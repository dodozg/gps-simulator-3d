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
};

// Fizički vjerodostojan raspon |ECEF| za sve što crtamo: površina ~6.37e6 m,
// GNSS sateliti MEO ~2.66e7, BDS GEO/IGSO ~4.22e7. Točka bliža ishodištu od
// donje granice je duboko u Zemlji (npr. kolabirana EKF procjena) i Cesium je
// NE MOŽE projicirati -> Cartographic.fromCartesian vrati undefined pa render
// loop pukne ("Cannot read properties of undefined (reading 'longitude')").
const R_MIN = 1e6;   // 1000 km od središta — ispod svake stvarne točke
const R_MAX = 1e9;   // daleko iza GEO — štit od divergentne procjene

// Vrati Cartesian3 samo ako su komponente konačne i magnituda projicirabilna;
// inače null (pozivatelj tada sakrije entitet umjesto da sruši render).
function c3(e: [number, number, number] | null | undefined): Cesium.Cartesian3 | null {
  if (!e) return null;
  const [x, y, z] = e;
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
  const r = Math.hypot(x, y, z);
  if (r < R_MIN || r > R_MAX) return null;
  return new Cesium.Cartesian3(x, y, z);
}

export class Globe {
  viewer: Cesium.Viewer;
  private meta: ConstellationMeta | null = null;
  private sats = new Map<string, Cesium.Entity>();
  private rays = new Map<string, Cesium.Entity>();
  private orbitInertial: Cesium.Cartesian3[][] = [];
  private orbitEntities: Cesium.Entity[] = [];
  private rover: Cesium.Entity | null = null;
  private estimate: Cesium.Entity | null = null;
  private show = { orbits: true, rays: true, labels: false };

  constructor(container: HTMLElement, onPlace: (lat: number, lon: number) => void) {
    const token = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;
    if (token) Cesium.Ion.defaultAccessToken = token;

    const opts: Cesium.Viewer.ConstructorOptions = {
      baseLayerPicker: false, geocoder: false, homeButton: false,
      sceneModePicker: false, navigationHelpButton: false, animation: false,
      timeline: false, fullscreenButton: false, infoBox: false,
      selectionIndicator: false, creditContainer: document.createElement("div"),
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
    this.viewer.clock.shouldAnimate = false;
    this.viewer.camera.flyHome(0);

    // Dvoklik na globus postavlja prijemnik.
    const handler = this.viewer.screenSpaceEventHandler;
    handler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
    handler.setInputAction((m: Cesium.ScreenSpaceEventHandler.PositionedEvent) => {
      const cart = this.viewer.camera.pickEllipsoid(m.position, s.globe.ellipsoid);
      if (!cart) return;
      const carto = Cesium.Cartographic.fromCartesian(cart);
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
  }

  private _updateOrbits(simTime: number): void {
    if (!this.meta) return;
    const theta = this.meta.omega_e * simTime; // ECEF = Rz(-theta) * inercijalno
    const ct = Math.cos(theta), st = Math.sin(theta);
    this.orbitEntities.forEach((ent, idx) => {
      if (!this.show.orbits) { ent.show = false; return; }
      ent.show = true;
      const pts = this.orbitInertial[idx].map((p) =>
        new Cesium.Cartesian3(p.x * ct + p.y * st, -p.x * st + p.y * ct, p.z),
      );
      (ent.polyline!.positions as unknown) = new Cesium.ConstantProperty(pts);
    });
  }

  private _satEntity(sat: SatFrame, pos: Cesium.Cartesian3): Cesium.Entity {
    let e = this.sats.get(sat.id);
    if (!e) {
      e = this.viewer.entities.add({
        id: `sat:${sat.id}`,
        position: pos,
        point: { pixelSize: 7, color: COL.sat, outlineColor: Cesium.Color.BLACK, outlineWidth: 1 },
        label: {
          text: sat.id, font: "11px monospace", fillColor: Cesium.Color.WHITE,
          pixelOffset: new Cesium.Cartesian2(0, -14), showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString("#0d1117cc"), show: false,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      this.sats.set(sat.id, e);
    }
    return e;
  }

  update(frame: StateFrame): void {
    // sateliti
    const seen = new Set<string>();
    for (const sat of frame.satellites) {
      const pos = c3(sat.ecef);
      if (!pos) { const ex = this.sats.get(sat.id); if (ex) ex.show = false; continue; }
      seen.add(sat.id);
      const e = this._satEntity(sat, pos);
      e.show = true;
      (e.position as Cesium.ConstantPositionProperty).setValue(pos);
      const col = sat.rejected ? COL.rejected : sat.tracked ? COL.tracked : COL.sat;
      e.point!.color = new Cesium.ConstantProperty(col);
      e.point!.pixelSize = new Cesium.ConstantProperty(sat.tracked ? 9 : 6);
      e.label!.show = new Cesium.ConstantProperty(this.show.labels);
    }
    for (const [id, e] of this.sats) if (!seen.has(id)) e.show = false;

    this._updateReceiver(frame);
    this._updateRays(frame);
    this._updateOrbits(frame.sim_time);
  }

  private _updateReceiver(frame: StateFrame): void {
    const rx = frame.receiver;
    const roverPos = rx.placed && rx.truth ? c3(rx.truth.ecef) : null;
    if (roverPos) {
      if (!this.rover) {
        this.rover = this.viewer.entities.add({
          position: roverPos,
          point: { pixelSize: 12, color: COL.rover, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
          billboard: undefined,
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
          point: { pixelSize: 9, color: COL.estimate, outlineColor: Cesium.Color.BLACK, outlineWidth: 1 },
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
    const rover = this.show.rays && rx.placed && rx.truth ? c3(rx.truth.ecef) : null;
    if (rover) {
      for (const sat of frame.satellites) {
        if (!sat.tracked) continue;
        const satPos = c3(sat.ecef);
        if (!satPos) continue;
        seen.add(sat.id);
        let ray = this.rays.get(sat.id);
        const pts = [rover, satPos];
        if (!ray) {
          ray = this.viewer.entities.add({
            polyline: { positions: pts, width: 1.2, material: COL.ray, arcType: Cesium.ArcType.NONE },
          });
          this.rays.set(sat.id, ray);
        } else {
          ray.show = true;
          (ray.polyline!.positions as unknown) = new Cesium.ConstantProperty(pts);
        }
      }
    }
    for (const [id, ray] of this.rays) if (!seen.has(id)) ray.show = false;
  }

  flyTo(lat: number, lon: number): void {
    this.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(lon, lat, 9_000_000),
      duration: 1.4,
    });
  }

  setShow(key: "orbits" | "rays" | "labels", on: boolean): void {
    this.show[key] = on;
  }
}
