import "cesium/Build/Cesium/Widgets/widgets.css";
import "./style.css";

import { Globe } from "./globe/globe";
import { SimSocket } from "./lib/ws";
import { api } from "./lib/api";
import { t, getLang, setLang, onLangChange } from "./lib/i18n";
import { getMode, setMode, onModeChange } from "./lib/prefs";
import { h } from "./lib/dom";
import { mountControls } from "./ui/controls";
import { mountFlyTo } from "./ui/flyto";
import { mountGlobeControls } from "./ui/globe-controls";
import { mountTelemetry } from "./ui/telemetry";
import { mountSatEditor } from "./ui/sat-editor";
import { mountDock } from "./ui/dock";
import { mountExperiments } from "./experiments/experiments";
import { mountLessons } from "./edu/lessons";
import { mountGuide } from "./edu/guide";
import { initInfo } from "./edu/info";
import type { StateFrame } from "./lib/types";

const ui = document.getElementById("ui")!;
const cesiumRoot = document.getElementById("cesium")!;

// --- ljuska sučelja ---
const header = h("header", "app-header");
const brand = h("div", "brand");
const brandTitle = h("div", "brand-title", t("app_title"));
const brandSub = h("div", "brand-sub", t("app_subtitle"));
brand.append(brandTitle, brandSub);

const status = h("div", "conn", t("connecting"));

const segLang = h("div", "seg");
const segMode = h("div", "seg");
function segBtn(label: string, active: boolean, cb: () => void): HTMLElement {
  const b = h("button", "seg-btn" + (active ? " active" : ""), label);
  b.addEventListener("click", cb);
  return b;
}
function renderHeader(): void {
  brandTitle.textContent = t("app_title");
  brandSub.textContent = t("app_subtitle");
  segLang.replaceChildren(
    segBtn("HR", getLang() === "hr", () => setLang("hr")),
    segBtn("EN", getLang() === "en", () => setLang("en")),
  );
  segMode.replaceChildren(
    segBtn(t("mode_beginner"), getMode() === "beginner", () => setMode("beginner")),
    segBtn(t("mode_expert"), getMode() === "expert", () => setMode("expert")),
  );
}
const headerRight = h("div", "header-right");
headerRight.append(status, segMode, segLang);
header.append(brand, headerRight);
ui.appendChild(header);

const leftPanel = h("aside", "panel panel-left");
const rightPanel = h("aside", "panel panel-right");
ui.append(leftPanel, rightPanel);

renderHeader();
onLangChange(renderHeader);
onModeChange(renderHeader);

// --- globus + veza ---
const globe = new Globe(cesiumRoot, (lat, lon) => {
  // NE pomiči kameru: korisnik je dvoklikom već pokazao točno kamo gleda.
  // (Prijašnji flyTo na 9000 km je odzumiravao i djelovao kao "drift".)
  socket.send({ type: "set_receiver", lat, lon });   // alt izostavljen -> teren (DEM)
});

const satEditor = mountSatEditor(ui, (msg) => socket.send(msg), (ecef) => globe.lookAtSat(ecef));
// Klik na satelit na globusu otvara njegov editor (kao klik na redak u tablici).
globe.onSatelliteClick((id) => satEditor.open(id));
const telemetry = mountTelemetry(rightPanel, (msg) => socket.send(msg), (id) => satEditor.open(id));
const dock = mountDock(ui);
const experiments = mountExperiments();
const info = initInfo();
let controls: ReturnType<typeof mountControls> | null = null;

// Lokacija prijemnika se pamti u localStorage pa prežive i RESTART servera (sesija
// se restartom vrati na "nepostavljeno"). Vraćamo je SAMO jednom nakon spajanja i
// samo ako je backend prazan (svjež) — da ne poništimo namjerni Reset korisnika.
const RX_KEY = "gps3d.receiver";
function loadRx(): { lat: number; lon: number } | null {
  try {
    const v = JSON.parse(localStorage.getItem(RX_KEY) || "null");
    return v && Number.isFinite(v.lat) && Number.isFinite(v.lon) ? v : null;
  } catch { return null; }
}
let needRxRestore = false;

function onFrame(f: StateFrame): void {
  telemetry.update(f);
  satEditor.update(f);
  globe.update(f);
  dock.update(f);
  info.setFrame(f);
  controls?.syncFromFrame(f);

  const rx = f.receiver;
  if (rx.placed && rx.truth) {
    try { localStorage.setItem(RX_KEY, JSON.stringify({ lat: rx.truth.lla.lat, lon: rx.truth.lla.lon })); }
    catch { /* localStorage nedostupan — ignoriraj */ }
    needRxRestore = false;
  } else if (needRxRestore) {
    needRxRestore = false;                          // pokušaj samo jednom po spajanju
    const savedRx = loadRx();
    if (savedRx) socket.send({ type: "set_receiver", lat: savedRx.lat, lon: savedRx.lon });
  }
}
function onStatus(s: "connecting" | "connected" | "disconnected"): void {
  status.textContent = s === "connected" ? t("connected")
    : s === "connecting" ? t("connecting") : t("disconnected");
  status.className = "conn " + s;
  // Pri (ponovnom) spajanju: uskladi kontrole i vrati spremljenu lokaciju prijemnika.
  if (s === "connected") { controls?.resync(); needRxRestore = true; }
}

const socket = new SimSocket(onFrame, onStatus);

// Pogon vođenih lekcija: koraci pogone panel (kroz controls.set da UI ostane
// usklađen), socket (postavljanje prijemnika), globus i eksperimente.
const lessons = mountLessons({
  place: (lat, lon) => socket.send({ type: "set_receiver", lat, lon }),
  attack: (v) => controls?.set({ attack: v }),
  timeOfDay: (hour) => controls?.set({ tow: hour * 3600 }),
  raim: (on) => controls?.set({ raim: on }),
  kinematic: (on) => controls?.set({ kinematic: on }),
  speed: (v) => controls?.set({ timeScale: v }),
  play: () => controls?.set({ playing: true }),
  pause: () => controls?.set({ playing: false }),
  reset: () => { socket.send({ type: "reset" }); controls?.set({ playing: false }); },
  experiment: (tab) => experiments.open(tab),
  flyTo: (lat, lon) => globe.flyTo(lat, lon),
});

const guide = mountGuide();
controls = mountControls(leftPanel, (msg) => socket.send(msg), globe,
  () => experiments.open(), () => lessons.open(), () => guide.open());

// "Fly to" pretraga (grad/koordinate) — plutajuća traka iznad globusa.
mountFlyTo(ui, globe, (lat, lon) => socket.send({ type: "set_receiver", lat, lon }));

// Kontrole globusa (kompas / 3D / centriranje / zoom) — dolje-desno.
mountGlobeControls(ui, globe);

api.constellation().then((meta) => globe.setMeta(meta)).catch(() => { /* orbite kasnije */ });
socket.connect();
onLangChange(() => onStatus("connected"));
