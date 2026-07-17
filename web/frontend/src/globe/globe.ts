// Cesium globus: sateliti, orbite, signalne zrake, rover — sve u ECEF-u
// (backend šalje ECEF metre, isti okvir kao Cesium fiksni frame).
import * as Cesium from "cesium";
import type { StateFrame, ConstellationMeta, SatFrame } from "../lib/types";

const COL = {
  rover: Cesium.Color.fromCssColorString("#fabf29"),
  estimate: Cesium.Color.fromCssColorString("#24d3ed"),
  sat: Cesium.Color.fromCssColorString("#8f9bb3"),
  tracked: Cesium.Color.fromCssColorString("#3dd899"),
  rejected: Cesium.Color.fromCssColorString("#f76b6b"),
  ray: Cesium.Color.fromCssColorString("#3dd899").withAlpha(0.5),
  orbit: Cesium.Color.fromCssColorString("#24d3ed").withAlpha(0.28),
  spoof: Cesium.Color.fromCssColorString("#f76b6b"),
  jam: Cesium.Color.fromCssColorString("#f76b6b").withAlpha(0.16),
};

// Cesium svaki frame za točke/oznake/polilinije PREDRAČUNA 2D-projiciranu
// poziciju: projection.project(Cartographic.fromCartesian(pos)). Ako pos mapira
// na undefined kartografsku (točka u središtu Zemlje, ili NaN), project dobije
// undefined -> "Cannot read properties of undefined (reading 'longitude')" i
// render loop se TRAJNO zaustavi. Zato ovdje radimo TOČNO istu provjeru koju
// Cesium radi interno i odbacimo poziciju koja se ne može projicirati.
// Oznaka satelita na zraki se stavlja ovoliko [m] iznad baze (uz smjer zrake) pa
// se oznake razdvoje po azimutu/elevaciji umjesto da se skupe u točki na roveru.
const RAY_LABEL_DIST = 5000;
// Oznake uz zrake vidljive samo kad je kamera bliže od ovoga [m] (zoomirano na
// rover); dalje se sakriju da ne zatrpaju prikacijom kad se gleda cijela scena.
const RAY_LABEL_MAX_CAM = 2_000_000;

const _scratch = new Cesium.Cartesian3();
function projectable(c: Cesium.Cartesian3): boolean {
  if (!Number.isFinite(c.x) || !Number.isFinite(c.y) || !Number.isFinite(c.z)) return false;
  // fromCartesian vrati undefined ako se točka ne može spustiti na elipsoid
  // (npr. središte). Isti poziv koji Cesium radi u primitives.update.
  return Cesium.Cartographic.fromCartesian(c, Cesium.Ellipsoid.WGS84, undefined) !== undefined;
}

// Vrati Cartesian3 samo ako je konačan i Cesium ga MOŽE projicirati; inače null
// (pozivatelj tada sakrije entitet umjesto da sruši render loop).
function c3(e: [number, number, number] | null | undefined): Cesium.Cartesian3 | null {
  if (!e) return null;
  const [x, y, z] = e;
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
  Cesium.Cartesian3.fromElements(x, y, z, _scratch);
  if (!projectable(_scratch)) return null;
  return new Cesium.Cartesian3(x, y, z);
}

export class Globe {
  viewer: Cesium.Viewer;
  private meta: ConstellationMeta | null = null;
  // Sateliti/zrake preko Primitive API-ja (PointPrimitive/Label/Polyline
  // Collection) — izbjegava per-frame re-evaluaciju svojstava koju rade Entity-ji;
  // bitno pri punom multi-GNSS (~96 sat.). Rover/estimate/orbite/napad ostaju
  // Entity-ji jer su malobrojni.
  private pointCol!: Cesium.PointPrimitiveCollection;
  private labelCol!: Cesium.LabelCollection;
  private polyCol!: Cesium.PolylineCollection;
  private satPoints = new Map<string, Cesium.PointPrimitive>();
  private satLabels = new Map<string, Cesium.Label>();
  private rays = new Map<string, Cesium.Polyline>();
  // Oznake satelita uz zrake, blizu rovera (vide se tek pri zoomu — vidi _updateRays).
  private rayLabels = new Map<string, Cesium.Label>();
  private orbitInertial: Cesium.Cartesian3[][] = [];
  private orbitEntities: Cesium.Entity[] = [];
  private rover: Cesium.Entity | null = null;
  private estimate: Cesium.Entity | null = null;
  private lastRoverLLA: { lat: number; lon: number } | null = null;
  private spoofArrow: Cesium.Entity | null = null;
  private spoofTarget: Cesium.Entity | null = null;
  private jamRing: Cesium.Entity | null = null;
  private show = { orbits: true, rays: true, labels: false };
  // Cache stila satelita (boja/veličina) da ne alociramo ConstantProperty svaki
  // frame kad se ništa nije promijenilo.
  private satStyle = new Map<string, { col: Cesium.Color; size: number }>();
  // Throttle orbita: rebuild samo kad se Zemljin kut osjetno pomakne.
  private lastOrbitTheta = NaN;
  private orbitsDirty = true;

  constructor(container: HTMLElement, onPlace: (lat: number, lon: number) => void) {
    const token = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;
    if (token) Cesium.Ion.defaultAccessToken = token;

    const opts: Cesium.Viewer.ConstructorOptions = {
      baseLayerPicker: false, geocoder: false, homeButton: false,
      sceneModePicker: false, navigationHelpButton: false, animation: false,
      timeline: false, fullscreenButton: false, infoBox: false,
      selectionIndicator: false, creditContainer: document.createElement("div"),
      // Renderiraj SAMO na zahtjev (novi podaci / pomak kamere), ne 60 fps u
      // prazno. scene.requestRender() zovemo na kraju update() i pri toggleovima.
      requestRenderMode: true, maximumRenderTimeChange: Infinity,
    };
    if (!token) {
      // Bez ion tokena: OpenStreetMap imagery + elipsoidni teren (bez tokena).
      opts.baseLayer = Cesium.ImageryLayer.fromProviderAsync(
        Promise.resolve(
          new Cesium.UrlTemplateImageryProvider({
            url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            credit: "© OpenStreetMap contributors",
            maximumLevel: 19,
          }),
        ),
        {},
      );
      opts.terrainProvider = new Cesium.EllipsoidTerrainProvider();
    }
    this.viewer = new Cesium.Viewer(container, opts);

    const s = this.viewer.scene;
    s.backgroundColor = Cesium.Color.fromCssColorString("#01050c");
    s.globe.enableLighting = true;
    if (s.skyAtmosphere) s.skyAtmosphere.show = true;
    s.fog.enabled = true;
    // Ograniči zoom-out: bez ovoga se kamera može odzumirati u beskonačnost (Zemlja
    // postane točka u praznom svemiru). Cap ~55 000 km drži CIJELU konstelaciju
    // (orbite na ~20–30 tis. km visine) u kadru s marginom, ali ne dalje.
    // minimumZoomDistance ostaje default (blizu, za precizno postavljanje rovera).
    s.screenSpaceCameraController.maximumZoomDistance = 55_000_000;
    this.viewer.clock.shouldAnimate = false;
    this.viewer.camera.flyHome(0);

    // Kolekcije primitiva za brojne dinamičke objekte (sateliti + zrake).
    this.pointCol = s.primitives.add(new Cesium.PointPrimitiveCollection());
    this.labelCol = s.primitives.add(new Cesium.LabelCollection());
    this.polyCol = s.primitives.add(new Cesium.PolylineCollection());

    // Sigurnosna mreža: Cesium nakon greške u render loopu TRAJNO stane i prikaže
    // crveni panel. Naši se podaci mijenjaju 10 Hz i loše stanje (npr. divergentna
    // procjena) je prolazno, pa gušimo panel i nastavljamo loop. Ako greška bude
    // uporna (>20 uzastopnih), odustanemo da ne opteretimo CPU.
    const widget = this.viewer.cesiumWidget as unknown as {
      showErrorPanel: (t: string, m?: string, e?: unknown) => void;
    };
    widget.showErrorPanel = () => { /* bez crvenog panela */ };
    let renderFails = 0;
    s.postRender.addEventListener(() => { renderFails = 0; });   // uspješan frame -> reset
    s.renderError.addEventListener((_scene, err) => {
      renderFails += 1;
      if (renderFails <= 20) {
        this.viewer.useDefaultRenderLoop = true;                 // nastavi (prolazna greška)
      } else if (renderFails === 21) {
        console.error("[globe] render loop zaustavljen nakon uzastopnih grešaka", err);
      }
    });

    // Dvoklik na globus postavlja prijemnik.
    const handler = this.viewer.screenSpaceEventHandler;
    handler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
    handler.setInputAction((m: Cesium.ScreenSpaceEventHandler.PositionedEvent) => {
      const cart = this.viewer.camera.pickEllipsoid(m.position, s.globe.ellipsoid);
      if (!cart) return;
      const carto = Cesium.Cartographic.fromCartesian(cart);
      if (!carto) return;
      onPlace(Cesium.Math.toDegrees(carto.latitude), Cesium.Math.toDegrees(carto.longitude));
    }, Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
  }

  setMeta(meta: ConstellationMeta): void {
    this.meta = meta;
    this._buildOrbits();
  }

  private _buildOrbits(): void {
    if (!this.meta) return;
    const { a, i, w, planes } = this.meta.gps;
    // Ako meta sadrži nekonačnu vrijednost, orbitne točke bi bile NaN -> polilinija
    // sruši render (project(undefined)). Radije ne crtaj orbite nego sruši globus.
    if (![a, i, w].every(Number.isFinite) || !planes.every(Number.isFinite)) return;
    const inc = Cesium.Math.toRadians(i);
    const wr = Cesium.Math.toRadians(w);
    const N = 128;
    this.orbitInertial = planes.map((lanDeg) => {
      const lan = Cesium.Math.toRadians(lanDeg);
      const pts: Cesium.Cartesian3[] = [];
      for (let k = 0; k <= N; k++) {
        const nu = (2 * Math.PI * k) / N;
        // kružnica radijusa a u orbitalnoj ravnini -> Rz(w) Rx(inc) Rz(lan)
        let x = a * Math.cos(nu), y = a * Math.sin(nu);
        let x1 = x * Math.cos(wr) - y * Math.sin(wr);
        let y1 = x * Math.sin(wr) + y * Math.cos(wr);
        const x2 = x1, y2 = y1 * Math.cos(inc), z2 = y1 * Math.sin(inc);
        const X = x2 * Math.cos(lan) - y2 * Math.sin(lan);
        const Y = x2 * Math.sin(lan) + y2 * Math.cos(lan);
        pts.push(new Cesium.Cartesian3(X, Y, z2));
      }
      return pts;
    });
    this.orbitEntities.forEach((e) => this.viewer.entities.remove(e));
    this.orbitEntities = this.orbitInertial.map(() =>
      this.viewer.entities.add({
        polyline: { positions: [], width: 1, material: COL.orbit, arcType: Cesium.ArcType.NONE },
      }),
    );
    this.orbitsDirty = true;
  }

  private _updateOrbits(simTime: number): void {
    if (!this.meta) return;
    if (!this.show.orbits) { this.orbitEntities.forEach((e) => { e.show = false; }); return; }
    const theta = this.meta.omega_e * simTime; // ECEF = Rz(-theta) * inercijalno
    if (!Number.isFinite(theta)) return;
    // Orbite se rotiraju sa Zemljom (sporo). Preskoči rebuild dok se kut nije
    // osjetno pomaknuo — inače alociramo N×129 Cartesian3 + ConstantProperty svaki
    // frame nizašto.
    if (!this.orbitsDirty && Math.abs(theta - this.lastOrbitTheta) < 0.002) {
      this.orbitEntities.forEach((e) => { e.show = true; });
      return;
    }
    this.lastOrbitTheta = theta;
    this.orbitsDirty = false;
    const ct = Math.cos(theta), st = Math.sin(theta);
    this.orbitEntities.forEach((ent, idx) => {
      ent.show = true;
      const pts = this.orbitInertial[idx].map((p) =>
        new Cesium.Cartesian3(p.x * ct + p.y * st, -p.x * st + p.y * ct, p.z),
      );
      (ent.polyline!.positions as unknown) = new Cesium.ConstantProperty(pts);
    });
  }

  // Osiguraj point+label primitiv za satelit (kreira ih pri prvom pojavljivanju).
  private _ensureSat(sat: SatFrame, pos: Cesium.Cartesian3): Cesium.PointPrimitive {
    let p = this.satPoints.get(sat.id);
    if (!p) {
      p = this.pointCol.add({
        position: pos, pixelSize: 7, color: COL.sat,
        outlineColor: Cesium.Color.BLACK, outlineWidth: 1,
      });
      this.satPoints.set(sat.id, p);
      const l = this.labelCol.add({
        position: pos, text: sat.id, font: "11px monospace", fillColor: Cesium.Color.WHITE,
        pixelOffset: new Cesium.Cartesian2(0, -14), showBackground: true,
        backgroundColor: Cesium.Color.fromCssColorString("#0d1117cc"), show: this.show.labels,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      });
      this.satLabels.set(sat.id, l);
    }
    return p;
  }

  update(frame: StateFrame): void {
    // sateliti (Primitive API — izravna, jeftina mutacija svojstava)
    const seen = new Set<string>();
    for (const sat of frame.satellites) {
      // Ugašeni sateliti (konstelacija/sat isključen) se ne crtaju.
      const pos = sat.enabled === false ? null : c3(sat.ecef);
      if (!pos) {
        const ep = this.satPoints.get(sat.id); if (ep) ep.show = false;
        const el = this.satLabels.get(sat.id); if (el) el.show = false;
        continue;
      }
      seen.add(sat.id);
      const p = this._ensureSat(sat, pos);
      const l = this.satLabels.get(sat.id)!;
      p.show = true;
      p.position = pos;
      l.position = pos;
      // Sakrij oznaku satelita ISPOD horizonta (el < 0): label ima isključen
      // depth-test pa bi inače "probijao" kroz Zemlju za satelite iza horizonta.
      // Bez postavljenog rovera (el nedostupan) prikaži sve kao i prije.
      l.show = this.show.labels && (sat.el == null || sat.el >= 0);
      // Boju/veličinu piši samo na promjenu.
      const col = sat.rejected ? COL.rejected : sat.tracked ? COL.tracked : COL.sat;
      const size = sat.tracked ? 9 : 6;
      const st = this.satStyle.get(sat.id);
      if (!st || st.col !== col || st.size !== size) {
        p.color = col;
        p.pixelSize = size;
        this.satStyle.set(sat.id, { col, size });
      }
    }
    for (const [id, p] of this.satPoints) {
      if (!seen.has(id)) { p.show = false; const l = this.satLabels.get(id); if (l) l.show = false; }
    }

    this._updateReceiver(frame);
    this._updateRays(frame);
    this._updateOrbits(frame.sim_time);
    this._updateAttack(frame);

    // requestRenderMode: podaci su se promijenili -> zatraži jedan render.
    this.viewer.scene.requestRender();
  }

  // Prostorni prikaz napada: spoof "pull" vektor (kamo napadač povlači rješenje)
  // i simbolički radijus jamminga. Sve se sakrije kad napad nije aktivan.
  private _updateAttack(frame: StateFrame): void {
    const ov = frame.attack_overlay;
    const rx = frame.receiver;
    const rover = rx.placed && rx.truth ? c3(rx.truth.ecef) : null;

    // --- koordinirani spoof: strelica truth -> lažni cilj ---
    const tgt = ov && ov.active && ov.type === "coordinated" && ov.target_ecef
      ? c3(ov.target_ecef) : null;
    if (rover && tgt) {
      const pts = [rover, tgt];
      if (!this.spoofArrow) {
        this.spoofArrow = this.viewer.entities.add({
          polyline: { positions: pts, width: 3, arcType: Cesium.ArcType.NONE,
            material: new Cesium.PolylineArrowMaterialProperty(COL.spoof) },
        });
        this.spoofTarget = this.viewer.entities.add({
          position: tgt,
          point: { pixelSize: 10, color: COL.spoof, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
          label: { text: "SPOOF", font: "bold 12px sans-serif", fillColor: COL.spoof,
            pixelOffset: new Cesium.Cartesian2(0, -16), showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString("#0d1117dd"),
            disableDepthTestDistance: Number.POSITIVE_INFINITY },
        });
      } else {
        this.spoofArrow.show = true;
        (this.spoofArrow.polyline!.positions as unknown) = new Cesium.ConstantProperty(pts);
        this.spoofTarget!.show = true;
        (this.spoofTarget!.position as Cesium.ConstantPositionProperty).setValue(tgt);
      }
    } else {
      if (this.spoofArrow) this.spoofArrow.show = false;
      if (this.spoofTarget) this.spoofTarget.show = false;
    }

    // --- jamming: crveni disk uskraćivanja oko prijemnika ---
    const jam = ov && ov.active && ov.type === "jamming" && rover ? ov : null;
    if (jam && rover) {
      const r = jam.radius_m ?? 25000;
      if (!this.jamRing) {
        this.jamRing = this.viewer.entities.add({
          position: rover,
          ellipse: { semiMajorAxis: r, semiMinorAxis: r, height: 0,
            material: COL.jam, outline: true, outlineColor: COL.spoof.withAlpha(0.6) },
          label: { text: "JAMMING", font: "bold 12px sans-serif", fillColor: COL.spoof,
            pixelOffset: new Cesium.Cartesian2(0, -18), showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString("#0d1117dd"),
            disableDepthTestDistance: Number.POSITIVE_INFINITY },
        });
      } else {
        this.jamRing.show = true;
        (this.jamRing.position as Cesium.ConstantPositionProperty).setValue(rover);
      }
    } else if (this.jamRing) {
      this.jamRing.show = false;
    }
  }

  private _updateReceiver(frame: StateFrame): void {
    const rx = frame.receiver;
    this.lastRoverLLA = rx.placed && rx.truth ? { lat: rx.truth.lla.lat, lon: rx.truth.lla.lon } : null;
    const roverPos = rx.placed && rx.truth ? c3(rx.truth.ecef) : null;
    if (roverPos) {
      if (!this.rover) {
        this.rover = this.viewer.entities.add({
          position: roverPos,
          // Prilijepi na tlo: prijemnik je na stvarnoj nadmorskoj visini (npr.
          // 167 m), a globus crta ravni elipsoid (visina 0). Bez ovoga marker
          // "lebdi" iznad površine pa na kutu/zoomu ispada pored klika i "klizi"
          // (paralaksa) pri pomicanju karte.
          point: { pixelSize: 12, color: COL.rover, outlineColor: Cesium.Color.WHITE, outlineWidth: 2,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY },
        });
      } else {
        this.rover.show = true;
        (this.rover.position as Cesium.ConstantPositionProperty).setValue(roverPos);
      }
    } else if (this.rover) {
      this.rover.show = false;
    }

    const estPos = rx.ekf_initialized && rx.estimate ? c3(rx.estimate.ecef) : null;
    if (estPos) {
      if (!this.estimate) {
        this.estimate = this.viewer.entities.add({
          position: estPos,
          point: { pixelSize: 9, color: COL.estimate, outlineColor: Cesium.Color.BLACK, outlineWidth: 1,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY },
        });
      } else {
        this.estimate.show = true;
        (this.estimate.position as Cesium.ConstantPositionProperty).setValue(estPos);
      }
    } else if (this.estimate) {
      this.estimate.show = false;
    }
  }

  private _updateRays(frame: StateFrame): void {
    const rx = frame.receiver;
    const seen = new Set<string>();
    // Baza zrake mora sjediti na POVRŠINI (visina 0), ne na stvarnoj nadmorskoj
    // visini prijemnika: globus crta ravni elipsoid pa bi zraka iz pune ECEF
    // visine (npr. 167 m) "lebdjela" iznad tla i klizila/paralaksirala pri
    // pomicanju karte — isti razlog zbog kojeg je rover marker CLAMP_TO_GROUND.
    // Polyline u PolylineCollection ne podržava heightReference, pa bazu ručno
    // projiciramo na elipsoid preko lat/lon (visina razlike je nevidljiva na
    // skali od 20 000 km do satelita).
    const lla = rx.placed && rx.truth ? rx.truth.lla : null;
    const rover = this.show.rays && lla && Number.isFinite(lla.lat) && Number.isFinite(lla.lon)
      ? Cesium.Cartesian3.fromDegrees(lla.lon, lla.lat, 0.0)
      : null;
    if (rover) {
      for (const sat of frame.satellites) {
        if (!sat.tracked) continue;
        const satPos = c3(sat.ecef);
        if (!satPos) continue;
        seen.add(sat.id);
        let ray = this.rays.get(sat.id);
        const pts = [rover, satPos];
        if (!ray) {
          ray = this.polyCol.add({
            positions: pts, width: 1.2,
            material: Cesium.Material.fromType("Color", { color: COL.ray }),
          });
          this.rays.set(sat.id, ray);
        } else {
          ray.show = true;
          ray.positions = pts;
        }

        // Oznaka satelita uz zraku, malo iznad baze prema satelitu — pri zoomu na
        // rover jasno pokazuje kojoj zraki pripada koji satelit. Skrivena kad je
        // kamera daleko (distanceDisplayCondition) da ne zatrpa cijeli prikaz.
        const dir = Cesium.Cartesian3.subtract(satPos, rover, new Cesium.Cartesian3());
        Cesium.Cartesian3.normalize(dir, dir);
        const labelPos = Cesium.Cartesian3.add(
          rover, Cesium.Cartesian3.multiplyByScalar(dir, RAY_LABEL_DIST, new Cesium.Cartesian3()),
          new Cesium.Cartesian3());
        let rl = this.rayLabels.get(sat.id);
        if (!rl) {
          rl = this.labelCol.add({
            position: labelPos, text: sat.id, font: "11px monospace",
            fillColor: COL.tracked, showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString("#0d1117cc"),
            pixelOffset: new Cesium.Cartesian2(0, -10),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0.0, RAY_LABEL_MAX_CAM),
          });
          this.rayLabels.set(sat.id, rl);
        } else {
          rl.show = true;
          rl.position = labelPos;
        }
      }
    }
    for (const [id, ray] of this.rays) if (!seen.has(id)) {
      ray.show = false;
      const rl = this.rayLabels.get(id); if (rl) rl.show = false;
    }
  }

  flyTo(lat: number, lon: number, height = 1_500_000): void {
    this.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(lon, lat, height),
      duration: 1.4,
    });
  }

  setShow(key: "orbits" | "rays" | "labels", on: boolean): void {
    this.show[key] = on;
    if (key === "labels") {
      for (const l of this.satLabels.values()) l.show = on;
    } else if (key === "orbits" && on) {
      this.orbitsDirty = true;
    }
    this.viewer.scene.requestRender();
  }

  // --- kontrole kamere (Google-Earth stil) ------------------------------
  zoomIn(): void {
    const c = this.viewer.camera;
    c.zoomIn(c.positionCartographic.height * 0.4);
  }
  zoomOut(): void {
    const c = this.viewer.camera;
    c.zoomOut(c.positionCartographic.height * 0.4);
  }
  // Postavi kurs (bearing) rotacijom oko točke u SREDIŠTU ekrana — kao kompas u
  // Google Maps (globus se okreće oko onoga što gledaš, kamera se ne "vrti u
  // mjestu"). headingRad: 0 = sjever gore, raste u smjeru kazaljke na satu.
  setHeading(headingRad: number): void {
    const scene = this.viewer.scene;
    const camera = scene.camera;
    const canvas = scene.canvas;
    const pivot = camera.pickEllipsoid(
      new Cesium.Cartesian2(canvas.clientWidth / 2, canvas.clientHeight / 2),
      scene.globe.ellipsoid);
    if (!pivot) {
      // Središte gleda u svemir (npr. cijela Zemlja) -> vrti kameru u mjestu.
      camera.setView({ orientation: { heading: headingRad, pitch: camera.pitch, roll: 0 } });
      scene.requestRender();
      return;
    }
    // Očitaj trenutni nagib i udaljenost u lokalnom (ENU) okviru pivota, pa
    // ponovno pogledaj pivot s istim nagibom/udaljenošću i novim kursom.
    camera.lookAtTransform(Cesium.Transforms.eastNorthUpToFixedFrame(pivot));
    const range = Cesium.Cartesian3.magnitude(camera.position);
    const pitch = camera.pitch;
    camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
    camera.lookAt(pivot, new Cesium.HeadingPitchRange(headingRad, pitch, range));
    camera.lookAtTransform(Cesium.Matrix4.IDENTITY);   // otpusti -> normalne kontrole
    scene.requestRender();
  }

  // Klik na kompas: poravnaj prikaz — sjever gore, bez nagiba (pogled ravno
  // odozgo, teren "horizontalan"), centriran na trenutnu točku u sredini ekrana.
  resetNorth(): void {
    const scene = this.viewer.scene;
    const camera = scene.camera;
    const canvas = scene.canvas;
    const pivot = camera.pickEllipsoid(
      new Cesium.Cartesian2(canvas.clientWidth / 2, canvas.clientHeight / 2),
      scene.globe.ellipsoid);
    let dest: Cesium.Cartesian3;
    if (pivot) {
      const carto = Cesium.Cartographic.fromCartesian(pivot);
      dest = Cesium.Cartesian3.fromRadians(
        carto.longitude, carto.latitude, camera.positionCartographic.height);  // zadrži zoom
    } else {
      dest = Cesium.Cartesian3.clone(camera.positionWC);
    }
    camera.flyTo({
      destination: dest,
      orientation: { heading: 0, pitch: -Cesium.Math.PI_OVER_TWO, roll: 0 },   // sjever gore, ravno dolje
      duration: 0.6,
    });
  }
  flyToReceiver(): boolean {
    if (!this.lastRoverLLA) return false;
    this.flyTo(this.lastRoverLLA.lat, this.lastRoverLLA.lon, 600_000);
    return true;
  }
  headingDeg(): number {
    return Cesium.Math.toDegrees(this.viewer.camera.heading);
  }
  // Igla kompasa mora pratiti kameru U REALNOM VREMENU dok korisnik vrti globus
  // mišem. `camera.changed` okida tek nakon praga i zna kasniti; `preRender` se
  // javi na SVAKI iscrtani frame (a s requestRenderMode-om iscrtavamo upravo
  // kad se nešto miče), pa je igla uvijek u koraku s globusom.
  onCameraChange(cb: () => void): void {
    this.viewer.scene.preRender.addEventListener(cb);
  }
}
