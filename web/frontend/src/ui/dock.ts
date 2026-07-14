// Donji dok: žive krivulje (greška / GDOP / NIS) + živi skyplot trenutnih
// satelita. Puni se iz svakog frame-a WebSocketa; crtanje je throttlano na
// requestAnimationFrame. Dok se može sklopiti/rasklopiti.
import { h, clear, term } from "../lib/dom";
import { t, onLangChange } from "../lib/i18n";
import { drawLine, drawSkyplot, legendChip, CHART_COLORS, type SkyPoint } from "./charts";
import type { StateFrame } from "../lib/types";

const CAP = 600; // koliko epoha čuvamo (klizni prozor)

export function mountDock(parent: HTMLElement) {
  const times: number[] = [];
  const errs: Array<number | null> = [];
  const gdops: Array<number | null> = [];
  const niss: Array<number | null> = [];
  let sats: SkyPoint[] = [];
  let placed = false;
  let open = localStorage.getItem("dock_open") !== "0";
  let dirty = false;

  const dock = h("div", "dock" + (open ? " open" : ""));
  const handle = h("button", "dock-handle", "");
  const body = h("div", "dock-body");
  dock.append(handle, body);
  parent.appendChild(dock);

  // struktura: skyplot + 3 mini grafa
  const skyCard = h("div", "dock-card");
  const skyHead = h("div", "dock-card-head");
  const skyCanvas = h("canvas", "dock-canvas sky") as HTMLCanvasElement;
  skyCard.append(skyHead, skyCanvas);

  function chartCard(titleNode: HTMLElement, canvas: HTMLCanvasElement, legend: HTMLElement): HTMLElement {
    const card = h("div", "dock-card");
    const head = h("div", "dock-card-head");
    head.append(titleNode, legend);
    card.append(head, canvas);
    return card;
  }
  const errCanvas = h("canvas", "dock-canvas") as HTMLCanvasElement;
  const gdopCanvas = h("canvas", "dock-canvas") as HTMLCanvasElement;
  const nisCanvas = h("canvas", "dock-canvas") as HTMLCanvasElement;

  const errHead = h("span", "dock-card-title");
  const gdopHead = h("span", "dock-card-title");
  const nisHead = h("span", "dock-card-title");
  const errLeg = h("div", "legend");
  const gdopLeg = h("div", "legend");
  const nisLeg = h("div", "legend");

  const errCard = chartCard(errHead, errCanvas, errLeg);
  const gdopCard = chartCard(gdopHead, gdopCanvas, gdopLeg);
  const nisCard = chartCard(nisHead, nisCanvas, nisLeg);

  function labels(): void {
    handle.textContent = (open ? "▾ " : "▸ ") + t("live_charts");
    clear(skyHead); skyHead.appendChild(h("span", "dock-card-title", t("live_skyplot")));
    errHead.textContent = t("error") + " (m)";
    clear(gdopHead); gdopHead.append(term("GDOP"), document.createTextNode(""));
    clear(nisHead); nisHead.append(term("NIS", "NIS/dof"));
    clear(errLeg); errLeg.appendChild(legendChip(CHART_COLORS.amber, t("error")));
    clear(gdopLeg); gdopLeg.appendChild(legendChip(CHART_COLORS.cyan, "GDOP"));
    clear(nisLeg);
    nisLeg.appendChild(legendChip(CHART_COLORS.green, "NIS/dof"));
    nisLeg.appendChild(legendChip(CHART_COLORS.dim, t("nis_ideal")));
  }

  body.append(skyCard, errCard, gdopCard, nisCard);
  labels();
  onLangChange(labels);

  handle.addEventListener("click", () => {
    open = !open;
    dock.classList.toggle("open", open);
    localStorage.setItem("dock_open", open ? "1" : "0");
    labels();
    if (open) { dirty = true; schedule(); }
  });

  function redraw(): void {
    dirty = false;
    if (!open) return;
    drawSkyplot(skyCanvas, sats, false);
    if (!placed) return;
    const win = { xLabel: "s" };
    drawLine(errCanvas, [{ label: "err", color: CHART_COLORS.amber, data: errs }],
      { x: times, yMin: 0, ...win });
    drawLine(gdopCanvas, [{ label: "gdop", color: CHART_COLORS.cyan, data: gdops }],
      { x: times, yMin: 0, ...win });
    drawLine(nisCanvas, [{ label: "nis", color: CHART_COLORS.green, data: niss }],
      { x: times, yMin: 0, hlines: [{ y: 1, color: CHART_COLORS.dim, dash: true }], ...win });
  }

  let raf = 0;
  function schedule(): void {
    if (raf) return;
    raf = requestAnimationFrame(() => { raf = 0; if (dirty) redraw(); });
  }

  window.addEventListener("resize", () => { dirty = true; schedule(); });

  return {
    update(f: StateFrame): void {
      const rx = f.receiver;
      // reset/premotavanje: sim_time skočio unatrag -> očisti prozor
      const lastT = times.length ? times[times.length - 1] : -Infinity;
      if (f.sim_time < lastT) { times.length = 0; errs.length = 0; gdops.length = 0; niss.length = 0; }
      placed = rx.placed;
      sats = f.satellites.map((s) => ({
        el: s.el ?? -1, az: s.az ?? 0,
        color: s.rejected ? CHART_COLORS.red : s.tracked ? CHART_COLORS.green : CHART_COLORS.dim,
        label: s.id, tracked: s.tracked,
      }));
      // dodaj epohu samo kad imamo rješenje/geometriju
      times.push(f.sim_time);
      errs.push(rx.error_m ?? null);
      gdops.push(rx.gdop ?? null);
      niss.push(rx.nis_ratio ?? null);
      if (times.length > CAP) { times.shift(); errs.shift(); gdops.shift(); niss.shift(); }
      dirty = true; schedule();
    },
    reset(): void {
      times.length = 0; errs.length = 0; gdops.length = 0; niss.length = 0;
      sats = []; dirty = true; schedule();
    },
  };
}
