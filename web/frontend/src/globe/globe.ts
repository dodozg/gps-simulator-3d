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
  selected: Cesium.Color.fromCssColorString("#ffcf3d"),   // istaknuti (odabrani) satelit
};

// Cesium svaki frame za točke/oznake/polilinije PREDRAČUNA 2D-projiciranu
// poziciju: projection.project(Cartographic.fromCartesian(pos)). Ako pos mapira
// na undefined kartografsku (točka u središtu Zemlje, ili NaN), project dobije
// undefined -> "Cannot read properties of undefined (reading 'longitude')" i
// render loop se TRAJNO zaustavi. Zato ovdje radimo TOČNO istu provjeru koju
// Cesium radi interno i odbacimo poziciju koja se ne može projicirati.
// Oznaka satelita uz zraku stoji na udaljenosti PROPORCIONALNOJ zoomu (udaljenosti
// kamere od rovera), pa je njen PRIVIDNI (zaslonski) odmak od rovera ~konstantan
// bez obzira na zoom — kako zumiraš prema roveru, oznaka mu se dinamički primiče.
// Poziciju svaki render osvježava _repositionRayLabels (na preRender).
const RAY_LABEL_SCREEN_FRAC = 0.16;   // odmak uz zraku = ovaj udio udaljenosti kamere
const RAY_LABEL_MIN = 30;             // [m] donja granica (ekstremni zoom-in)
const RAY_LABEL_MAX = 400_000;        // [m] gornja granica (ekstremni zoom-out)

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
  // Oznake satelita uz zrake, blizu rovera; poziciju im dinamički skalira zoom.
  private rayLabels = new Map<string, Cesium.Label>();
  private rayRover: Cesium.Cartesian3 | null = null;      // baza zrake (rover)
  private rayGeom = new Map<string, Cesium.Cartesian3>(); // jedinični smjer zrake po satelitu
  private satClickCb: ((id: string) => void) | null = null; // klik na satelit -> editor
  private selectedSat: string | null = null;                // istaknuti (u editoru otvoreni) satelit
  private lastFrame: StateFrame | null = null;              // za restyle pri promjeni odabira (pauza)
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
  private satStyle = new Map<string, string>();   // cache stila (ključ) po satelitu
  // Throttle orbita: rebuild samo kad se Zemljin kut osjetno pomakne.
  private lastOrbitTheta = NaN;
  private orbitsDirty = true;
  // Koliko se miš pomaknuo tijekom trenutnog pritiska (px) — da razlikujemo
  // povlačenje (rotacija globusa) od čistog klika (odabir satelita).
  private dragMovedPx = 0;

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
    // postane točka u praznom svemiru). Cap ~150 000 km je dovoljno da CIJELA
    // konstelacija (najviši sateliti ~30 tis. km) stane u kadar s marginom za
    // oznake, ali ne dalje. minimumZoomDistance ostaje default (blizu, za rover).
    s.screenSpaceCameraController.maximumZoomDistance = 150_000_000;
    // Sjeverni pol drži "gore": bez ovoga se odzumirani globus (malen na ekranu)
    // pri povlačenju preko praznog neba počne kotrljati/prevrtati oko osi pogleda
    // umjesto urednog vrtnje oko polarne osi. UNIT_Z veže rotaciju na Z-os pa se
    // globus ponaša kao pravi globus (horizontalno = vrtnja, vertikalno = nagib).
    this.viewer.camera.constrainedAxis = Cesium.Cartesian3.UNIT_Z;
    this.viewer.clock.shouldAnimate = false;
    this.viewer.camera.flyHome(0);

    // Kolekcije primitiva za brojne dinamičke objekte (sateliti + zrake).
    this.pointCol = s.primitives.add(new Cesium.PointPrimitiveCollection());
    this.labelCol = s.primitives.add(new Cesium.LabelCollection());
    this.polyCol = s.primitives.add(new Cesium.PolylineCollection());

    // Oznake uz zrake se primiču/odmiču s zoomom (odmak ∝ udaljenosti kamere) pa
    // ostaju na ~istom zaslonskom položaju od rovera. Zato ih repozicioniramo na
    // SVAKI render (uklj. pomak/zoom kamere), ne samo pri novom podatkovnom frameu.
    s.preRender.addEventListener(() => this._repositionRayLabels());

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

    // Klik na satelit (točku, oznaku ili oznaku uz zraku) otvara njegov editor —
    // isto kao klik na redak u tablici satelita. Sve te primitive nose `id = sat.id`.
    handler.setInputAction((m: Cesium.ScreenSpaceEventHandler.PositionedEvent) => {
      // GPU pick (točka/oznaka nose id=sat.id); ako promaši — točke su sitne, a
      // pod requestRenderMode pick zna biti nepouzdan — fallback na najbliži
      // satelit u zaslonskom prostoru.
      if (this.dragMovedPx > 6) return;   // bilo je povlačenje (rotacija), ne klik
      const picked = this.viewer.scene.pick(m.position) as { id?: unknown } | undefined;
      let id: string | null =
        typeof picked?.id === "string" && this.satPoints.has(picked.id) ? picked.id : null;
      if (!id) id = this._nearestSatOnScreen(m.position);
      if (id) this.satClickCb?.(id);
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    // --- Rotacija globusa "kao Google Earth" ---------------------------------
    // Zadana Cesiumova rotacija "uhvati točku pod kursorom i vuci je" prestane
    // raditi čim kursor izađe izvan globusa. Umjesto toga orbitiramo kameru oko
    // SREDIŠTA Zemlje ovisno o SMJERU povlačenja: rotateRight = vrtnja oko polarne
    // osi, rotateUp = nagib (uz constrainedAxis=Z staje na polu, bez prevrtanja).
    // Kut ∝ pomaku miša kroz vidno polje (FOV/visina), pa je na globusu osjećaj
    // ~1:1 sa površinom, a izvan globusa se rotacija nastavlja u istom smjeru.
    s.screenSpaceCameraController.enableRotate = false;
    let dragging = false;
    handler.setInputAction(() => { dragging = true; this.dragMovedPx = 0; },
      Cesium.ScreenSpaceEventType.LEFT_DOWN);
    handler.setInputAction(() => { dragging = false; },
      Cesium.ScreenSpaceEventType.LEFT_UP);
    handler.setInputAction((m: Cesium.ScreenSpaceEventHandler.MotionEvent) => {
      if (!dragging) return;
      const dx = m.endPosition.x - m.startPosition.x;
      const dy = m.endPosition.y - m.startPosition.y;
      this.dragMovedPx += Math.hypot(dx, dy);
      const h = s.canvas.clientHeight || 1;
      const fovy = (s.camera.frustum as Cesium.PerspectiveFrustum).fovy ?? Math.PI / 3;
      const k = fovy / h;                 // radijana po pikselu (kroz vidno polje)
      s.camera.rotateRight(-dx * k);      // povuci desno -> globus (površina) ide desno
      s.camera.rotateUp(dy * k);          // povuci dolje -> globus ide dolje
      s.requestRender();
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
  }

  // Najbliži VIDLJIVI satelit u zaslonskom prostoru (px) — pouzdan fallback za pick.
  private _nearestSatOnScreen(win: Cesium.Cartesian2): string | null {
    const scene = this.viewer.scene;
    // Sfera Zemlje kao okluder — satelit iza horizonta nije klikabilan.
    const occluder = new Cesium.Occluder(
      new Cesium.BoundingSphere(Cesium.Cartesian3.ZERO, scene.globe.ellipsoid.minimumRadius),
      scene.camera.positionWC);
    const scr = new Cesium.Cartesian2();
    let best: string | null = null;
    let bestD = 22;   // prag [px]
    for (const [id, p] of this.satPoints) {
      if (!p.show || !occluder.isPointVisible(p.position)) continue;   // skriven / iza horizonta
      const s = Cesium.SceneTransforms.worldToWindowCoordinates(scene, p.position, scr);
      if (!s) continue;
      const d = Math.hypot(s.x - win.x, s.y - win.y);
      if (d < bestD) { bestD = d; best = id; }
    }
    return best;
  }

  // Callback kad se klikne satelit na globusu (postavlja main.ts -> otvori editor).
  onSatelliteClick(cb: (id: string) => void): void {
    this.satClickCb = cb;
  }

  // Doleti kamerom da satelit bude u kadru (gumb "Fokusiraj" u editoru satelita).
  lookAtSat(ecef: [number, number, number]): void {
    const target = c3(ecef);
    if (!target) return;
    this.viewer.camera.flyToBoundingSphere(new Cesium.BoundingSphere(target, 2_000_000), { duration: 1.0 });
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
        id: sat.id,   // za pick (klik na satelit otvara editor)
      });
      this.satPoints.set(sat.id, p);
      const l = this.labelCol.add({
        position: pos, text: sat.id, font: "11px monospace", fillColor: Cesium.Color.WHITE,
        pixelOffset: new Cesium.Cartesian2(0, -14), showBackground: true,
        backgroundColor: Cesium.Color.fromCssColorString("#0d1117cc"), show: this.show.labels,
        // NE isključuj depth-test: Zemlja mora zakloniti oznake satelita koji su
        // fizički iza globusa (inače "lebde" ispred globusa i zbunjuju).
        id: sat.id,
      });
      this.satLabels.set(sat.id, l);
    }
    return p;
  }

  // Boja/veličina/isticanje satelita; piše u primitiv SAMO kad se ključ promijeni.
  // Odabrani (u editoru otvoreni) satelit dobije veći biljeg + zlatni obrub, a
  // zadržava boju statusa (praćen/odbačen) da se ne izgubi informacija.
  private _styleSat(p: Cesium.PointPrimitive, sat: SatFrame): void {
    const selected = sat.id === this.selectedSat;
    const status = sat.rejected ? "r" : sat.tracked ? "t" : "s";
    const key = status + (selected ? "S" : "");
    if (this.satStyle.get(sat.id) === key) return;
    p.color = sat.rejected ? COL.rejected : sat.tracked ? COL.tracked : COL.sat;
    p.pixelSize = (sat.tracked ? 9 : 6) + (selected ? 6 : 0);
    p.outlineColor = selected ? COL.selected : Cesium.Color.BLACK;
    p.outlineWidth = selected ? 3 : 1;
    this.satStyle.set(sat.id, key);
  }

  // Istakni odabrani (u editoru otvoreni) satelit; null poništava. Restyle radimo
  // odmah za stari+novi (i kad je sim pauziran, bez novih frameova).
  setSelectedSat(id: string | null): void {
    if (this.selectedSat === id) return;
    const prev = this.selectedSat;
    this.selectedSat = id;
    for (const sid of [prev, id]) {
      if (!sid) continue;
      const p = this.satPoints.get(sid);
      const s = this.lastFrame?.satellites.find((x) => x.id === sid);
      if (p && s) this._styleSat(p, s);
    }
    this.viewer.scene.requestRender();
  }

  update(frame: StateFrame): void {
    this.lastFrame = frame;
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
      // Zaklanjanje globusom rješava depth-test (label više NEMA disableDepthTestDistance):
      // satelit iza Zemlje se sam sakrije. Prekidač "oznake" je jedini dodatni uvjet.
      l.show = this.show.labels;
      this._styleSat(p, sat);   // boja/veličina/isticanje — piše samo na promjenu
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
    this.rayRover = rover;
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

        // Oznaka satelita uz zraku — spremi samo SMJER; stvarnu poziciju (odmak od
        // rovera proporcionalan zoomu) postavlja _repositionRayLabels na preRender.
        const dir = Cesium.Cartesian3.normalize(
          Cesium.Cartesian3.subtract(satPos, rover, new Cesium.Cartesian3()), new Cesium.Cartesian3());
        this.rayGeom.set(sat.id, dir);
        let rl = this.rayLabels.get(sat.id);
        if (!rl) {
          rl = this.labelCol.add({
            position: rover, text: sat.id, font: "11px monospace",
            fillColor: COL.tracked, showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString("#0d1117cc"),
            pixelOffset: new Cesium.Cartesian2(0, -10),
            // Bez disableDepthTestDistance: kad je rover s druge strane globusa,
            // Zemlja zakloni i oznake uz zrake (ne "probijaju" kroz planet).
            show: this.show.labels,   // dijele isti "oznake" prekidač kao satelitske oznake
            id: sat.id,               // klik na oznaku uz zraku isto otvara editor
          });
          this.rayLabels.set(sat.id, rl);
        } else {
          rl.show = this.show.labels;
        }
      }
    }
    for (const [id, ray] of this.rays) if (!seen.has(id)) {
      ray.show = false;
      const rl = this.rayLabels.get(id); if (rl) rl.show = false;
    }
    this._repositionRayLabels();
  }

  // Odmak oznaka uz zrake od rovera skalira s udaljenošću kamere (zoomom) pa je
  // njihov zaslonski položaj ~konstantan bez obzira na zoom. Zove se svaki render
  // (preRender), pa se dinamički primiču dok zumiraš prema roveru.
  private _repositionRayLabels(): void {
    const rover = this.rayRover;
    if (!rover) return;
    const camDist = Cesium.Cartesian3.distance(this.viewer.camera.positionWC, rover);
    const off = Math.min(Math.max(camDist * RAY_LABEL_SCREEN_FRAC, RAY_LABEL_MIN), RAY_LABEL_MAX);
    const scaled = new Cesium.Cartesian3();
    for (const [id, lbl] of this.rayLabels) {
      if (!lbl.show) continue;
      const dir = this.rayGeom.get(id);
      if (!dir) continue;
      lbl.position = Cesium.Cartesian3.add(
        rover, Cesium.Cartesian3.multiplyByScalar(dir, off, scaled), new Cesium.Cartesian3());
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
      // Oznake uz zrake dijele isti prekidač; kad se pale, prikaži samo one čija
      // je zraka vidljiva (praćeni sateliti) pa ih pravilno pozicioniraj.
      for (const [id, rl] of this.rayLabels) rl.show = on && (this.rays.get(id)?.show ?? false);
      if (on) this._repositionRayLabels();
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
