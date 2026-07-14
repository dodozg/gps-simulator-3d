// Grafovi bez vanjskih ovisnosti (canvas). Paleta se čita iz CSS varijabli pa
// prati temu. Dvije primitive: LineChart (višeserijski vremenski graf) i
// Skyplot (polarni el/az prikaz). NaN/null u nizu = prekid linije (rupa).

function cssVar(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
function palette() {
  return {
    grid: cssVar("--border", "#1e2836"),
    text: cssVar("--dim", "#8b98ab"),
    fg: cssVar("--text", "#e6edf3"),
    cyan: cssVar("--cyan", "#24d3ed"),
    green: cssVar("--green", "#3dd899"),
    amber: cssVar("--amber", "#fabf29"),
    red: cssVar("--red", "#f76b6b"),
  };
}

function fitCanvas(canvas: HTMLCanvasElement): { ctx: CanvasRenderingContext2D; w: number; h: number } {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(1, Math.floor(rect.width));
  const h = Math.max(1, Math.floor(rect.height));
  canvas.width = Math.floor(w * dpr);
  canvas.height = Math.floor(h * dpr);
  const ctx = canvas.getContext("2d")!;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

export interface Series {
  label: string;
  color: string;
  data: Array<number | null>;
}
export interface LineOpts {
  x?: number[];              // zajednička os x (default: indeksi)
  yMin?: number;             // fiksni min (inače auto)
  yMax?: number;             // fiksni max (inače auto)
  yLabel?: string;
  xLabel?: string;
  bands?: Array<{ from: number; to: number; color: string }>; // vertikalne trake (npr. prozor napada)
  hlines?: Array<{ y: number; color: string; dash?: boolean }>; // horizontalne referentne linije
}

const PAD = { l: 44, r: 10, t: 10, b: 22 };

function niceExtent(lo: number, hi: number): [number, number] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (lo === hi) { const d = Math.abs(lo) || 1; return [lo - d * 0.5, hi + d * 0.5]; }
  const pad = (hi - lo) * 0.08;
  return [lo - pad, hi + pad];
}

export function drawLine(canvas: HTMLCanvasElement, series: Series[], opts: LineOpts = {}): void {
  const P = palette();
  const { ctx, w, h } = fitCanvas(canvas);
  const n = Math.max(...series.map((s) => s.data.length), 0);
  if (n === 0) return;
  const xs = opts.x ?? Array.from({ length: n }, (_, i) => i);

  // y raspon
  let lo = opts.yMin ?? Infinity, hi = opts.yMax ?? -Infinity;
  if (opts.yMin == null || opts.yMax == null) {
    for (const s of series) for (const v of s.data) {
      if (v == null || !Number.isFinite(v)) continue;
      if (opts.yMin == null) lo = Math.min(lo, v);
      if (opts.yMax == null) hi = Math.max(hi, v);
    }
    for (const hl of opts.hlines ?? []) { if (opts.yMin == null) lo = Math.min(lo, hl.y); if (opts.yMax == null) hi = Math.max(hi, hl.y); }
    [lo, hi] = niceExtent(lo, hi);
  }
  const xlo = xs[0], xhi = xs[xs.length - 1] || 1;
  const px = (x: number) => PAD.l + ((x - xlo) / (xhi - xlo || 1)) * (w - PAD.l - PAD.r);
  const py = (y: number) => h - PAD.b - ((y - lo) / (hi - lo || 1)) * (h - PAD.t - PAD.b);

  // trake (bands)
  for (const b of opts.bands ?? []) {
    ctx.fillStyle = b.color;
    const x0 = px(Math.max(b.from, xlo)), x1 = px(Math.min(b.to, xhi));
    ctx.fillRect(x0, PAD.t, Math.max(0, x1 - x0), h - PAD.t - PAD.b);
  }

  // grid + y oznake
  ctx.strokeStyle = P.grid; ctx.fillStyle = P.text; ctx.lineWidth = 1;
  ctx.font = "10px " + cssVar("--mono", "monospace");
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  const TICKS = 4;
  for (let i = 0; i <= TICKS; i++) {
    const y = lo + ((hi - lo) * i) / TICKS;
    const yy = py(y);
    ctx.globalAlpha = 0.5; ctx.beginPath(); ctx.moveTo(PAD.l, yy); ctx.lineTo(w - PAD.r, yy); ctx.stroke(); ctx.globalAlpha = 1;
    const lbl = Math.abs(y) >= 1000 ? (y / 1000).toFixed(1) + "k" : Math.abs(y) < 1 && y !== 0 ? y.toFixed(2) : y.toFixed(0);
    ctx.fillText(lbl, PAD.l - 5, yy);
  }
  // x oznake (start/mid/end)
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  for (const frac of [0, 0.5, 1]) {
    const xv = xlo + (xhi - xlo) * frac;
    ctx.fillText(String(Math.round(xv)), px(xv), h - PAD.b + 4);
  }
  if (opts.xLabel) { ctx.textAlign = "right"; ctx.fillText(opts.xLabel, w - PAD.r, h - PAD.b + 4); }

  // referentne linije
  for (const hl of opts.hlines ?? []) {
    ctx.strokeStyle = hl.color; ctx.setLineDash(hl.dash ? [4, 4] : []); ctx.globalAlpha = 0.8;
    ctx.beginPath(); ctx.moveTo(PAD.l, py(hl.y)); ctx.lineTo(w - PAD.r, py(hl.y)); ctx.stroke();
    ctx.setLineDash([]); ctx.globalAlpha = 1;
  }

  // serije
  ctx.lineWidth = 1.6; ctx.lineJoin = "round";
  for (const s of series) {
    ctx.strokeStyle = s.color; ctx.beginPath();
    let pen = false;
    for (let i = 0; i < s.data.length; i++) {
      const v = s.data[i];
      if (v == null || !Number.isFinite(v)) { pen = false; continue; }
      const X = px(xs[i] ?? i), Y = py(v);
      if (!pen) { ctx.moveTo(X, Y); pen = true; } else ctx.lineTo(X, Y);
    }
    ctx.stroke();
  }
}

export interface SkyPoint { el: number; az: number; color: string; label?: string; tracked?: boolean; }

export function drawSkyplot(canvas: HTMLCanvasElement, points: SkyPoint[], showLabels = false): void {
  const P = palette();
  const { ctx, w, h } = fitCanvas(canvas);
  const cx = w / 2, cy = h / 2;
  const R = Math.max(10, Math.min(w, h) / 2 - 14);
  // el=90 u centru, el=0 na rubu
  const rOf = (el: number) => R * (1 - Math.max(0, Math.min(90, el)) / 90);
  const pos = (el: number, az: number) => {
    const r = rOf(el), a = (az - 90) * Math.PI / 180; // sjever gore, azimut u smjeru kazaljke
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)] as const;
  };

  ctx.strokeStyle = P.grid; ctx.fillStyle = P.text; ctx.lineWidth = 1;
  ctx.font = "9px " + cssVar("--mono", "monospace");
  for (const el of [0, 30, 60]) {
    ctx.globalAlpha = 0.6; ctx.beginPath(); ctx.arc(cx, cy, rOf(el), 0, 2 * Math.PI); ctx.stroke(); ctx.globalAlpha = 1;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    if (el > 0) ctx.fillText(el + "°", cx, cy - rOf(el));
  }
  // radijalne linije + strane svijeta
  ctx.globalAlpha = 0.5;
  for (let a = 0; a < 360; a += 45) {
    const [x, y] = pos(0, a); ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(x, y); ctx.stroke();
  }
  ctx.globalAlpha = 1; ctx.fillStyle = P.text;
  const dirs: Array<[string, number]> = [["N", 0], ["E", 90], ["S", 180], ["W", 270]];
  for (const [d, az] of dirs) {
    const [x, y] = pos(-6, az);
    ctx.fillText(d, x, y);
  }

  for (const p of points) {
    if (!Number.isFinite(p.el) || !Number.isFinite(p.az) || p.el < 0) continue;
    const [x, y] = pos(p.el, p.az);
    ctx.beginPath(); ctx.arc(x, y, p.tracked ? 5 : 3.5, 0, 2 * Math.PI);
    ctx.fillStyle = p.color; ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = "#04141a"; ctx.stroke();
    if (showLabels && p.label) {
      ctx.fillStyle = P.fg; ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.fillText(p.label, x + 7, y);
    }
  }
}

// Pomoćnik: chip legende (DOM) da su nazivi lokalizirani i van canvasa.
export function legendChip(color: string, label: string): HTMLElement {
  const el = document.createElement("span");
  el.className = "legend-chip";
  const dot = document.createElement("span");
  dot.className = "legend-dot";
  dot.style.background = color;
  el.appendChild(dot);
  el.appendChild(document.createTextNode(label));
  return el;
}

export const CHART_COLORS = {
  get cyan() { return palette().cyan; },
  get green() { return palette().green; },
  get amber() { return palette().amber; },
  get red() { return palette().red; },
  get dim() { return palette().text; },
};
