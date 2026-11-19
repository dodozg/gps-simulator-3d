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

// ---- Graf metrike vs parametar s vrpcom intervala pouzdanosti (sandbox) ----
// Svaka serija: srednje vrijednosti u točkama x + donja/gornja granica CI-ja
// (null = nema podatka). Os x je brojčana (opcionalno log) ili kategorijska
// (xLabels: oznake za x = 0, 1, 2, …).
export interface CiSeries {
  label: string;
  color: string;
  x: number[];
  mean: Array<number | null>;
  lo: Array<number | null>;
  hi: Array<number | null>;
}
export interface CiOpts {
  xLabels?: string[];
  logX?: boolean;
  xLabel?: string;
  yMin?: number;
}

function fmtTick(v: number): string {
  const a = Math.abs(v);
  if (a === 0) return "0";
  if (a >= 1000) return (v / 1000).toFixed(a >= 10000 ? 0 : 1) + "k";
  if (a < 0.01) return v.toExponential(0);
  if (a < 1) return v.toFixed(2);
  if (a < 10) return v.toFixed(1);
  return v.toFixed(0);
}

export function drawCiChart(canvas: HTMLCanvasElement, series: CiSeries[], opts: CiOpts = {}): void {
  const P = palette();
  const { ctx, w, h } = fitCanvas(canvas);
  const ok = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);
  const tx = (x: number) => (opts.logX ? Math.log10(Math.max(x, 1e-300)) : x);
  let xlo = Infinity, xhi = -Infinity, lo = opts.yMin ?? Infinity, hi = -Infinity;
  for (const s of series) {
    s.x.forEach((x, i) => {
      xlo = Math.min(xlo, tx(x)); xhi = Math.max(xhi, tx(x));
      for (const v of [s.mean[i], s.lo[i], s.hi[i]]) {
        if (!ok(v)) continue;
        if (opts.yMin == null) lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    });
  }
  if (!Number.isFinite(xlo)) return;
  [lo, hi] = niceExtent(lo, hi);
  if (opts.yMin != null) lo = opts.yMin;
  if (opts.xLabels) { xlo = -0.5; xhi = opts.xLabels.length - 0.5; }
  else if (xlo === xhi) { xlo -= 1; xhi += 1; }
  const L = 52;
  const px = (x: number) => L + ((tx(x) - xlo) / (xhi - xlo || 1)) * (w - L - PAD.r);
  const py = (y: number) => h - PAD.b - ((y - lo) / (hi - lo || 1)) * (h - PAD.t - PAD.b);

  ctx.strokeStyle = P.grid; ctx.fillStyle = P.text; ctx.lineWidth = 1;
  ctx.font = "10px " + cssVar("--mono", "monospace");
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (let i = 0; i <= 4; i++) {
    const y = lo + ((hi - lo) * i) / 4, yy = py(y);
    ctx.globalAlpha = 0.5; ctx.beginPath(); ctx.moveTo(L, yy); ctx.lineTo(w - PAD.r, yy); ctx.stroke(); ctx.globalAlpha = 1;
    ctx.fillText(fmtTick(y), L - 5, yy);
  }
  // x oznake: kategorije, ili sve različite vrijednosti x (najviše ~10)
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  if (opts.xLabels) {
    opts.xLabels.forEach((lab, i) => ctx.fillText(lab, px(i), h - PAD.b + 4));
  } else {
    const xs = Array.from(new Set(series.flatMap((s) => s.x))).sort((a, b) => a - b);
    const stepN = Math.max(1, Math.ceil(xs.length / 10));
    xs.forEach((x, i) => { if (i % stepN === 0) ctx.fillText(fmtTick(x), px(x), h - PAD.b + 4); });
  }
  if (opts.xLabel) { ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillText(opts.xLabel, L + 4, PAD.t + 2); }

  const nS = series.length;
  series.forEach((s, si) => {
    // kategorijski x: mali pomak po seriji da se trake ne preklapaju
    const off = opts.xLabels ? (si - (nS - 1) / 2) * Math.min(14, 60 / Math.max(nS, 1)) : 0;
    const idx = s.x.map((_, i) => i).sort((a, b) => s.x[a] - s.x[b]);
    // vrpca CI-ja (poligon gornja granica → donja natrag), prekida se na rupama
    ctx.fillStyle = s.color; ctx.globalAlpha = 0.16;
    let seg: number[] = [];
    const flush = () => {
      if (seg.length >= 2 && !opts.xLabels) {
        ctx.beginPath();
        seg.forEach((i, k) => { const X = px(s.x[i]), Y = py(s.hi[i] as number); if (k === 0) ctx.moveTo(X, Y); else ctx.lineTo(X, Y); });
        for (let k = seg.length - 1; k >= 0; k--) { const i = seg[k]; ctx.lineTo(px(s.x[i]), py(s.lo[i] as number)); }
        ctx.closePath(); ctx.fill();
      }
      seg = [];
    };
    for (const i of idx) { if (ok(s.lo[i]) && ok(s.hi[i])) seg.push(i); else flush(); }
    flush();
    ctx.globalAlpha = 1;
    // kategorijski: okomite trake pogreške
    if (opts.xLabels) {
      ctx.strokeStyle = s.color; ctx.lineWidth = 1.4;
      for (const i of idx) {
        if (!ok(s.lo[i]) || !ok(s.hi[i])) continue;
        const X = px(s.x[i]) + off;
        ctx.beginPath(); ctx.moveTo(X, py(s.lo[i] as number)); ctx.lineTo(X, py(s.hi[i] as number));
        ctx.moveTo(X - 4, py(s.lo[i] as number)); ctx.lineTo(X + 4, py(s.lo[i] as number));
        ctx.moveTo(X - 4, py(s.hi[i] as number)); ctx.lineTo(X + 4, py(s.hi[i] as number));
        ctx.stroke();
      }
    }
    // linija srednje vrijednosti + točke
    ctx.strokeStyle = s.color; ctx.fillStyle = s.color; ctx.lineWidth = 1.8;
    ctx.beginPath();
    let pen = false;
    for (const i of idx) {
      const v = s.mean[i];
      if (!ok(v)) { pen = false; continue; }
      const X = px(s.x[i]) + off, Y = py(v);
      if (!pen || opts.xLabels) { ctx.moveTo(X, Y); pen = true; } else ctx.lineTo(X, Y);
    }
    if (!opts.xLabels) ctx.stroke();
    for (const i of idx) {
      const v = s.mean[i];
      if (!ok(v)) continue;
      ctx.beginPath(); ctx.arc(px(s.x[i]) + off, py(v), 3, 0, 2 * Math.PI); ctx.fill();
    }
  });
}

// Dodatne boje za više serija (uz CHART_COLORS).
export const EXTRA_COLORS = ["#bc8cff", "#ff9bce", "#7ee787", "#f0883e"];
