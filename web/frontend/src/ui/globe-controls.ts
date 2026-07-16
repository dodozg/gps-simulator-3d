// Kontrole globusa u Google-Earth stilu (desno-sredina): kompas (sjever, klik =
// sjever-gore), "centriraj na prijemnik", zoom +/−.
import { h } from "../lib/dom";
import { t } from "../lib/i18n";
import type { Globe } from "../globe/globe";

// Kompas: crvena polovica igle = sjever, siva = jug. Rotira se SAMO igla
// (.gc-needle) s −heading da pokazuje pravi sjever; bočne zakrivljene strelice
// (.gc-rot) su statična naznaka da se kompas može povlačiti za rotaciju globusa.
const COMPASS_SVG = `
<svg viewBox="0 0 40 40" width="36" height="36" aria-hidden="true">
  <g class="gc-rot" fill="none" stroke="#cbd5e1" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
    <path d="M8 15 A 10 10 0 0 0 8 25"/>
    <path d="M8 25 l 3.2 -0.5 M8 25 l -0.5 -3.2"/>
    <path d="M32 15 A 10 10 0 0 1 32 25"/>
    <path d="M32 25 l -3.2 -0.5 M32 25 l 0.5 -3.2"/>
  </g>
  <g class="gc-needle">
    <polygon points="20,6 24.5,21 20,17.5 15.5,21" fill="#f76b6b"/>
    <polygon points="20,34 24.5,19 20,22.5 15.5,19" fill="#8b98ab"/>
  </g>
</svg>`;

function btn(cls: string, title: string, inner: string): HTMLButtonElement {
  const b = h("button", "gc-btn " + cls) as HTMLButtonElement;
  b.title = title;
  b.innerHTML = inner;
  return b;
}

export function mountGlobeControls(parent: HTMLElement, globe: Globe): void {
  const box = h("div", "globe-controls");

  const compass = btn("gc-compass", t("gc_north"), COMPASS_SVG);
  const needle = compass.querySelector(".gc-needle") as SVGElement;   // rotira se samo igla

  // Kut pokazivača (radijani) od 12 sata, u smjeru kazaljke.
  let dragging = false, moved = false;
  function angleUp(ev: PointerEvent): number {
    const r = compass.getBoundingClientRect();
    return Math.atan2(ev.clientX - (r.left + r.width / 2), -(ev.clientY - (r.top + r.height / 2)));
  }
  compass.addEventListener("pointerdown", (ev) => {
    dragging = true; moved = false;
    compass.classList.add("dragging");
    compass.setPointerCapture(ev.pointerId);
    ev.preventDefault();
  });
  compass.addEventListener("pointermove", (ev) => {
    if (!dragging) return;
    moved = true;
    const a = angleUp(ev);
    globe.setHeading(-a);                                   // heading = −kut igle
    needle.style.transform = `rotate(${(a * 180) / Math.PI}deg)`;   // trenutni feedback
  });
  const endDrag = (ev: PointerEvent): void => {
    if (!dragging) return;
    compass.releasePointerCapture(ev.pointerId);
    compass.classList.remove("dragging");
    const wasDrag = moved;
    dragging = false;
    if (!wasDrag) globe.resetNorth();                       // klik bez pomaka = sjever gore
  };
  compass.addEventListener("pointerup", endDrag);
  compass.addEventListener("pointercancel", endDrag);

  const locate = btn("gc-locate", t("gc_locate"),
    `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
       <circle cx="12" cy="12" r="6"/><line x1="12" y1="1" x2="12" y2="4"/>
       <line x1="12" y1="20" x2="12" y2="23"/><line x1="1" y1="12" x2="4" y2="12"/>
       <line x1="20" y1="12" x2="23" y2="12"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/>
     </svg>`);
  locate.addEventListener("click", () => {
    if (!globe.flyToReceiver()) {
      box.classList.add("gc-miss");
      setTimeout(() => box.classList.remove("gc-miss"), 500);
    }
  });

  const zoomIn = btn("gc-zoom", t("gc_zoom_in"), "+");
  zoomIn.addEventListener("click", () => globe.zoomIn());
  const zoomOut = btn("gc-zoom", t("gc_zoom_out"), "−");
  zoomOut.addEventListener("click", () => globe.zoomOut());
  const zoomGroup = h("div", "gc-zoom-group");
  zoomGroup.append(zoomIn, zoomOut);

  box.append(compass, locate, zoomGroup);
  parent.appendChild(box);

  // Igla prati kurs kamere (globus -> igla). Preskoči za vrijeme povlačenja jer
  // je tada igla vođena kursorom (igla -> globus).
  const sync = () => { if (!dragging) needle.style.transform = `rotate(${-globe.headingDeg()}deg)`; };
  globe.onCameraChange(sync);
  sync();
}
