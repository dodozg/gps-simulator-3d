import "cesium/Build/Cesium/Widgets/widgets.css";
import "./style.css";

import { Globe } from "./globe/globe";
import { SimSocket } from "./lib/ws";
import { api } from "./lib/api";
import { t, getLang, setLang, onLangChange } from "./lib/i18n";
import { getMode, setMode, onModeChange } from "./lib/prefs";
import { h } from "./lib/dom";
import { mountControls } from "./ui/controls";
import { mountTelemetry } from "./ui/telemetry";
import { mountDock } from "./ui/dock";
import { mountExperiments } from "./experiments/experiments";
import { initGlossary } from "./edu/glossary";
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
  socket.send({ type: "set_receiver", lat, lon, alt: 100 });
  globe.flyTo(lat, lon);
});

const telemetry = mountTelemetry(rightPanel);
const dock = mountDock(ui);
const experiments = mountExperiments();
let controls: ReturnType<typeof mountControls> | null = null;

function onFrame(f: StateFrame): void {
  telemetry.update(f);
  globe.update(f);
  dock.update(f);
  controls?.syncFromFrame(f);
}
function onStatus(s: "connecting" | "connected" | "disconnected"): void {
  status.textContent = s === "connected" ? t("connected")
    : s === "connecting" ? t("connecting") : t("disconnected");
  status.className = "conn " + s;
}

const socket = new SimSocket(onFrame, onStatus);
controls = mountControls(leftPanel, (msg) => socket.send(msg), globe, () => experiments.open());

api.constellation().then((meta) => globe.setMeta(meta)).catch(() => { /* orbite kasnije */ });
void initGlossary();
socket.connect();
onLangChange(() => onStatus("connected"));
