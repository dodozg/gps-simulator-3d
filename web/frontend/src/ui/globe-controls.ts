// Kontrole globusa u Google-Earth stilu (dolje-desno): kompas (sjever, klik =
// sjever-gore), 2D/3D nagib, "centriraj na prijemnik", zoom +/−.
import { h } from "../lib/dom";
import { t } from "../lib/i18n";
import type { Globe } from "../globe/globe";

// Kompas: crvena polovica = sjever, siva = jug; "N" gore. Cijeli se rotira s
// -heading da strelica uvijek pokazuje pravi sjever na ekranu.
const COMPASS_SVG = `
<svg viewBox="0 0 40 40" width="30" height="30" aria-hidden="true">
  <polygon points="20,5 26,22 20,18 14,22" fill="#f76b6b"/>
  <polygon points="20,35 26,18 20,22 14,18" fill="#8b98ab"/>
  <text x="20" y="12" text-anchor="middle" font-size="8" font-weight="700" fill="#e6edf3" font-family="sans-serif">N</text>
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
  const needle = compass.querySelector("svg") as SVGElement;
  compass.addEventListener("click", () => globe.resetNorth());

  const mode3d = btn("gc-3d", t("gc_3d"), globe.is3D() ? "2D" : "3D");
  mode3d.addEventListener("click", () => {
    const now3d = globe.toggle3D();
    mode3d.textContent = now3d ? "2D" : "3D";   // gumb pokazuje kamo prebacuje
  });

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

  box.append(compass, mode3d, locate, zoomGroup);
  parent.appendChild(box);

  // Rotiraj iglu kompasa prema trenutnom kursu kamere.
  const sync = () => { needle.style.transform = `rotate(${-globe.headingDeg()}deg)`; };
  globe.onCameraChange(sync);
  sync();
}
