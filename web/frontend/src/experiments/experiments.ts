// Panel eksperimenata (Faza 2): RTK, spoofing/jamming, multi-GNSS, ionosfera.
// Forma -> REST (/api/*) -> rezultat (brojke + grafovi) + edukativna kartica
// fizike. Sve crtanje ide kroz canvas primitive iz ui/charts.
import { h, clear } from "../lib/dom";
import { t, getLang, onLangChange, type Lang } from "../lib/i18n";
import { api } from "../lib/api";
import { drawLine, legendChip, CHART_COLORS } from "../ui/charts";

// ---- oblici odgovora backenda (vidi web/backend/routes_experiments.py) ----
interface RtkRes { ok: boolean; reason?: string; baseline_m: number; n_common: number; n_epochs: number; float_err_m: number; fixed_err_m: number; ar_success: boolean; }
interface IonoRes { hours: number[]; dz: number[]; peak: [number, number]; night: number; elevs: number[]; slant: number[]; if_residual: number; l1_at20: number; }
interface MgSol { pos_err: number; pdop: number; n: number; systems: string[]; isb_est: Record<string, number>; }
interface MgRes { gps: [number, MgSol | null]; all: [number, MgSol | null]; sweep: { mask: number[]; gps_n: number[]; all_n: number[]; gps_pdop: number[]; all_pdop: number[] }; sys_bias: Record<string, number>; mask: number; }
interface SpoofRes { times: number[]; tracked: number[]; errors: Array<[number, number]>; gdops: number[]; target_err: number[]; alarms: Array<[number, string]>; fix_lost: number[]; attack_name: string; attack_desc: string; window: [number, number]; }
interface ScnMeta { file: string; name: string; description: string; lat: number; lon: number; seconds: number; attack: string | null; }
interface ScnMetrics { solved: number; total: number; median_err: number; conv_p95: number; max_err: number; gdop_median: number; raim_alarms: number; fix_lost: number; takeover_m: number | null; win_median_err: number | null; }
interface ScnRun { scenario: string; raim: boolean; result: ScnMetrics; }
interface ScnCompare { mode: string; a: { name: string; result: ScnMetrics }; b: { name: string; result: ScnMetrics }; }

type Field = { key: string; label: () => string; def: number; min?: number; max?: number; step?: number };

// Edukativne kartice (dulji tekst) — dvojezično, izvan i18n radi preglednosti.
const EDU: Record<string, Record<Lang, string>> = {
  rtk: {
    hr: "RTK koristi fazu nosioca (valna duljina ~19 cm), a ne kôd (~300 m čip). Dvostruke razlike (rover−baza, sat−sat) ukidaju satove i atmosferu. Ostaje cjelobrojna višeznačnost N (broj cijelih ciklusa) — kad je 'fiksiran' na cijeli broj, greška padne s decimetara (float) na milimetre (fixed).",
    en: "RTK uses the carrier phase (wavelength ~19 cm) instead of the code (~300 m chip). Double differences (rover−base, sat−sat) cancel clocks and the atmosphere. What remains is the integer ambiguity N (whole cycles) — once 'fixed' to an integer, error drops from decimetres (float) to millimetres (fixed).",
  },
  spoofing: {
    hr: "Napadi se ubrizgavaju na razinu mjerenja pa prolaze kroz pravi EKF/RAIM. Koordinirani spoof šalje konzistentnu laž — RAIM ne alarmira (temeljno ograničenje). Naivni multi-SV pomiče satelite nezavisno pa ih robusni RAIM izolira. Jamming diže šum: broj satelita pada i fix se gubi (uskraćivanje, ne obmana).",
    en: "Attacks are injected at the measurement level, so they pass through the real EKF/RAIM. A coordinated spoof sends a self-consistent lie — RAIM does not alarm (a fundamental limit). A naive multi-SV shifts satellites independently, so robust RAIM isolates them. Jamming raises the noise floor: satellite count drops and the fix is lost (denial, not deception).",
  },
  multignss: {
    hr: "Više konstelacija (GPS+Galileo+GLONASS+BeiDou) = više vidljivih satelita, niži PDOP i fix i u urbanom kanjonu gdje GPS sam vidi < 4 satelita. Svaki sustav ima svoju vremensku skalu pa prijemnik uz položaj i vlastiti sat procjenjuje i inter-system bias (ISB) kao dodatnu nepoznanicu.",
    en: "More constellations (GPS+Galileo+GLONASS+BeiDou) = more visible satellites, lower PDOP, and a fix even in an urban canyon where GPS alone sees < 4. Each system has its own time scale, so alongside position and its own clock the receiver also estimates the inter-system bias (ISB) as an extra unknown.",
  },
  iono: {
    hr: "Ionosfera usporava signal ovisno o gustoći slobodnih elektrona (TEC), koja je najveća ~14 h lokalno i najmanja noću. Klobuchar model to opisuje. Kašnjenje ovisi o frekvenciji (∝ 1/f²) pa dvofrekvencijska iono-free kombinacija (L1/L2) gotovo egzaktno poništava grešku; jednofrekvencijski prijemnik nosi puni iznos.",
    en: "The ionosphere slows the signal by an amount set by the free-electron density (TEC), highest around 14:00 local and lowest at night. The Klobuchar model captures this. Delay is frequency-dependent (∝ 1/f²), so the dual-frequency iono-free combination (L1/L2) cancels the error almost exactly; a single-frequency receiver carries the full amount.",
  },
  scenarios: {
    hr: "Scenarij fiksira SVE što određuje simulaciju (lokacija, trajanje, sjeme RNG-a, doba dana, napad) pa reprodukcija istog JSON-a daje bajt-identične metrike — idealno za poštenu usporedbu algoritama. 'Usporedi' vrti isti scenarij s RAIM-om uključenim i isključenim: kod naivnog spoofa razlika je dramatična (RAIM izolira lažne satelite), a kod koordiniranog spoofa RAIM ne pomaže jer je laž konzistentna.",
    en: "A scenario fixes EVERYTHING that determines the simulation (location, duration, RNG seed, time of day, attack), so replaying the same JSON yields byte-identical metrics — ideal for a fair algorithm comparison. 'Compare' runs the same scenario with RAIM on and off: for a naive spoof the difference is dramatic (RAIM isolates the fake satellites), while for a coordinated spoof RAIM does not help because the lie is self-consistent.",
  },
};

function edu(id: string): string { return EDU[id][getLang()]; }

export function mountExperiments() {
  const overlay = h("div", "modal-overlay");
  overlay.style.display = "none";
  const modal = h("div", "modal");
  const head = h("div", "modal-head");
  const title = h("div", "modal-title");
  const closeBtn = h("button", "modal-close", "✕");
  head.append(title, closeBtn);
  const tabsBar = h("div", "modal-tabs");
  const content = h("div", "modal-content");
  modal.append(head, tabsBar, content);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  closeBtn.addEventListener("click", close);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });

  let active = "rtk";

  const EXPS: Array<{ id: string; title: () => string; body: (root: HTMLElement) => void }> = [
    { id: "rtk", title: () => t("exp_rtk"), body: rtkPanel },
    { id: "spoofing", title: () => t("exp_spoofing"), body: spoofPanel },
    { id: "multignss", title: () => t("exp_multignss"), body: mgPanel },
    { id: "iono", title: () => t("exp_iono"), body: ionoPanel },
    { id: "scenarios", title: () => t("scenarios"), body: scenarioPanel },
  ];

  function renderTabs(): void {
    clear(tabsBar);
    for (const e of EXPS) {
      const b = h("button", "modal-tab" + (e.id === active ? " active" : ""), e.title());
      b.addEventListener("click", () => { active = e.id; renderTabs(); renderActive(); });
      tabsBar.appendChild(b);
    }
    title.textContent = t("experiments");
  }
  function renderActive(): void {
    clear(content);
    EXPS.find((e) => e.id === active)!.body(content);
  }

  onLangChange(() => { renderTabs(); renderActive(); });

  function open(tab?: string): void {
    if (tab) active = tab;
    overlay.style.display = "flex";
    renderTabs(); renderActive();
  }
  function close(): void { overlay.style.display = "none"; }

  return { open, close };
}

// ---------- zajednički gradbeni blokovi ----------

function form(fields: Field[], onRun: (vals: Record<string, number>, btn: HTMLButtonElement) => void): HTMLElement {
  const wrap = h("div", "exp-form");
  const inputs: Record<string, HTMLInputElement> = {};
  for (const f of fields) {
    const cell = h("div", "exp-field");
    cell.appendChild(h("label", "exp-flabel", f.label()));
    const inp = h("input", "exp-input") as HTMLInputElement;
    inp.type = "number"; inp.value = String(f.def);
    if (f.min != null) inp.min = String(f.min);
    if (f.max != null) inp.max = String(f.max);
    if (f.step != null) inp.step = String(f.step);
    inputs[f.key] = inp;
    cell.appendChild(inp);
    wrap.appendChild(cell);
  }
  const runBtn = h("button", "btn primary exp-run", t("run")) as HTMLButtonElement;
  runBtn.addEventListener("click", () => {
    const vals: Record<string, number> = {};
    for (const f of fields) vals[f.key] = Number(inputs[f.key].value);
    onRun(vals, runBtn);
  });
  const cell = h("div", "exp-field exp-run-cell");
  cell.appendChild(runBtn);
  wrap.appendChild(cell);
  return wrap;
}

function eduCard(id: string): HTMLElement {
  const c = h("div", "exp-edu");
  c.appendChild(h("div", "exp-edu-title", t("how_it_works")));
  c.appendChild(h("div", "exp-edu-body", edu(id)));
  return c;
}
function metric(label: string, value: string, cls = ""): HTMLElement {
  const m = h("div", "exp-metric " + cls);
  m.appendChild(h("div", "exp-metric-v", value));
  m.appendChild(h("div", "exp-metric-l", label));
  return m;
}
function busy(host: HTMLElement): void { clear(host); host.appendChild(h("div", "exp-busy", t("running"))); }
function fail(host: HTMLElement, msg: string): void { clear(host); host.appendChild(h("div", "exp-fail", msg)); }
function canvasCard(titleText: string, legend?: HTMLElement): { card: HTMLElement; canvas: HTMLCanvasElement } {
  const card = h("div", "exp-chart-card");
  const head = h("div", "exp-chart-head");
  head.appendChild(h("span", "exp-chart-title", titleText));
  if (legend) head.appendChild(legend);
  const canvas = h("canvas", "exp-canvas") as HTMLCanvasElement;
  card.append(head, canvas);
  return { card, canvas };
}
const LOC = { lat: 45.815, lon: 15.982 }; // Zagreb kao zadana lokacija

// ---------- RTK ----------
function rtkPanel(root: HTMLElement): void {
  root.appendChild(eduCard("rtk"));
  const out = h("div", "exp-out");
  root.appendChild(form([
    { key: "lat", label: () => t("f_lat"), def: LOC.lat, step: 0.001 },
    { key: "lon", label: () => t("f_lon"), def: LOC.lon, step: 0.001 },
    { key: "base_east_km", label: () => t("f_base_km"), def: 5, min: 0, max: 60 },
    { key: "n_epochs", label: () => t("f_epochs"), def: 40, min: 4, max: 120 },
    { key: "mask_deg", label: () => t("f_mask"), def: 15, min: 0, max: 40 },
  ], async (v, btn) => {
    btn.disabled = true; busy(out);
    try {
      const base = { lat: v.lat, lon: v.lon + (v.base_east_km / 111.32) / Math.cos(v.lat * Math.PI / 180), alt: 120 };
      const d = await api.rtk({ rover: { lat: v.lat, lon: v.lon, alt: 120 }, base,
        n_epochs: v.n_epochs, mask_deg: v.mask_deg }) as unknown as RtkRes;
      clear(out);
      if (!d.ok) { fail(out, d.reason ?? "—"); return; }
      const row = h("div", "exp-metrics");
      const floatCm = d.float_err_m * 100, fixedCm = d.fixed_err_m * 100;
      row.append(
        metric(t("m_float"), floatCm.toFixed(1) + " cm"),
        metric(t("m_fixed"), fixedCm.toFixed(2) + " cm", d.ar_success ? "good" : ""),
        metric(t("m_ar"), d.ar_success ? t("yes") : t("no"), d.ar_success ? "good" : "bad"),
        metric(t("m_baseline"), (d.baseline_m / 1000).toFixed(2) + " km"),
        metric(t("m_common_sats"), String(d.n_common)),
      );
      out.appendChild(row);
      const gain = floatCm / Math.max(fixedCm, 1e-6);
      out.appendChild(h("div", "exp-note", t("rtk_gain").replace("{x}", gain.toFixed(0))));
    } catch (e) { fail(out, String(e)); } finally { btn.disabled = false; }
  }));
  root.appendChild(out);
}

// ---------- Spoofing ----------
function spoofPanel(root: HTMLElement): void {
  root.appendChild(eduCard("spoofing"));
  const attackSel = h("select", "exp-select") as HTMLSelectElement;
  const ATTACKS: Array<[string, () => string]> = [
    ["none", () => t("atk_none")], ["coordinated", () => t("atk_coordinated")],
    ["naive", () => t("atk_naive")], ["meaconing", () => t("atk_meaconing")],
    ["jamming", () => t("atk_jamming")],
  ];
  for (const [val, lab] of ATTACKS) { const o = h("option", undefined, lab()) as HTMLOptionElement; o.value = val; attackSel.appendChild(o); }
  attackSel.value = "coordinated";
  const selCell = h("div", "exp-field");
  selCell.appendChild(h("label", "exp-flabel", t("f_attack")));
  selCell.appendChild(attackSel);

  const out = h("div", "exp-out");
  const f = form([
    { key: "lat", label: () => t("f_lat"), def: LOC.lat, step: 0.001 },
    { key: "lon", label: () => t("f_lon"), def: LOC.lon, step: 0.001 },
    { key: "seconds", label: () => t("f_seconds"), def: 300, min: 60, max: 900 },
  ], async (v, btn) => {
    btn.disabled = true; busy(out);
    try {
      const d = await api.spoofing({ lat: v.lat, lon: v.lon, alt: 120, seconds: v.seconds,
        attack: attackSel.value === "none" ? null : attackSel.value }) as unknown as SpoofRes;
      clear(out);
      out.appendChild(h("div", "exp-note", d.attack_desc));
      const errSeries = d.errors.map(([, e]) => e);
      const xs = d.errors.map(([tt]) => tt);
      const maxErr = Math.max(...errSeries, 1);
      const row = h("div", "exp-metrics");
      row.append(
        metric(t("m_maxerr"), maxErr < 1000 ? maxErr.toFixed(0) + " m" : (maxErr / 1000).toFixed(1) + " km", maxErr > 100 ? "bad" : "good"),
        metric(t("m_alarms"), String(d.alarms.length), d.alarms.length ? "good" : ""),
        metric(t("m_fixlost"), String(d.fix_lost.length), d.fix_lost.length ? "bad" : "good"),
      );
      out.appendChild(row);
      const leg = h("div", "legend");
      leg.append(legendChip(CHART_COLORS.amber, t("error")), legendChip(CHART_COLORS.red, t("atk_window")));
      const { card, canvas } = canvasCard(t("error") + " (m)", leg);
      out.appendChild(card);
      const bands = d.window[1] > d.window[0]
        ? [{ from: d.window[0], to: d.window[1], color: "rgba(247,107,107,0.16)" }] : [];
      requestAnimationFrame(() => drawLine(canvas,
        [{ label: "err", color: CHART_COLORS.amber, data: errSeries }],
        { x: xs, yMin: 0, xLabel: "s", bands }));
      // sateliti kroz vrijeme
      const leg2 = h("div", "legend"); leg2.appendChild(legendChip(CHART_COLORS.green, t("sats")));
      const { card: c2, canvas: cv2 } = canvasCard(t("sats"), leg2);
      out.appendChild(c2);
      requestAnimationFrame(() => drawLine(cv2,
        [{ label: "sats", color: CHART_COLORS.green, data: Array.from(d.tracked) }],
        { x: Array.from(d.times), yMin: 0, xLabel: "s" }));
    } catch (e) { fail(out, String(e)); } finally { btn.disabled = false; }
  });
  f.insertBefore(selCell, f.lastChild);
  root.append(f, out);
}

// ---------- Multi-GNSS ----------
function mgPanel(root: HTMLElement): void {
  root.appendChild(eduCard("multignss"));
  const out = h("div", "exp-out");
  root.appendChild(form([
    { key: "lat", label: () => t("f_lat"), def: LOC.lat, step: 0.001 },
    { key: "lon", label: () => t("f_lon"), def: LOC.lon, step: 0.001 },
    { key: "mask_deg", label: () => t("f_mask"), def: 10, min: 0, max: 40 },
  ], async (v, btn) => {
    btn.disabled = true; busy(out);
    try {
      const d = await api.multignss({ lat: v.lat, lon: v.lon, alt: 120, mask_deg: v.mask_deg }) as unknown as MgRes;
      clear(out);
      const [gN, gSol] = d.gps, [aN, aSol] = d.all;
      const row = h("div", "exp-metrics");
      row.append(
        metric(t("m_gps_sats"), String(gN)),
        metric(t("m_all_sats"), String(aN), "good"),
        metric("PDOP GPS", gSol ? gSol.pdop.toFixed(2) : t("no_fix_short"), gSol ? "" : "bad"),
        metric("PDOP " + t("m_all"), aSol ? aSol.pdop.toFixed(2) : t("no_fix_short"), "good"),
      );
      out.appendChild(row);
      // availability sweep (broj satelita po maski)
      const leg = h("div", "legend");
      leg.append(legendChip(CHART_COLORS.dim, "GPS"), legendChip(CHART_COLORS.green, t("m_all")));
      const { card, canvas } = canvasCard(t("mg_avail"), leg);
      out.appendChild(card);
      requestAnimationFrame(() => drawLine(canvas, [
        { label: "gps", color: CHART_COLORS.dim, data: d.sweep.gps_n },
        { label: "all", color: CHART_COLORS.green, data: d.sweep.all_n },
      ], { x: d.sweep.mask, yMin: 0, xLabel: "° " + t("f_mask"), hlines: [{ y: 4, color: CHART_COLORS.red, dash: true }] }));
      // PDOP po maski
      const leg2 = h("div", "legend");
      leg2.append(legendChip(CHART_COLORS.dim, "GPS"), legendChip(CHART_COLORS.cyan, t("m_all")));
      const { card: c2, canvas: cv2 } = canvasCard("PDOP", leg2);
      out.appendChild(c2);
      requestAnimationFrame(() => drawLine(cv2, [
        { label: "gps", color: CHART_COLORS.dim, data: d.sweep.gps_pdop.map((x) => (Number.isFinite(x) ? x : null)) },
        { label: "all", color: CHART_COLORS.cyan, data: d.sweep.all_pdop.map((x) => (Number.isFinite(x) ? x : null)) },
      ], { x: d.sweep.mask, yMin: 0, yMax: 12, xLabel: "° " + t("f_mask") }));
      // ISB tablica
      if (aSol) {
        const tbl = h("table", "exp-table");
        const hr = h("tr"); [t("isb_system"), t("isb_true"), t("isb_est")].forEach((c) => hr.appendChild(h("th", undefined, c)));
        tbl.appendChild(hr);
        for (const sys of Object.keys(d.sys_bias)) {
          if (sys === "GPS") continue;
          const tr = h("tr");
          tr.appendChild(h("td", "mono", sys));
          tr.appendChild(h("td", "mono", d.sys_bias[sys].toFixed(2) + " m"));
          tr.appendChild(h("td", "mono", aSol.isb_est[sys] != null ? aSol.isb_est[sys].toFixed(2) + " m" : "—"));
          tbl.appendChild(tr);
        }
        const wrap = h("div", "exp-chart-card");
        wrap.appendChild(h("div", "exp-chart-title", "Inter-system bias (ISB)"));
        wrap.appendChild(tbl);
        out.appendChild(wrap);
      }
    } catch (e) { fail(out, String(e)); } finally { btn.disabled = false; }
  }));
  root.appendChild(out);
}

// ---------- Ionosfera ----------
function ionoPanel(root: HTMLElement): void {
  root.appendChild(eduCard("iono"));
  const out = h("div", "exp-out");
  root.appendChild(form([
    { key: "lat", label: () => t("f_lat"), def: LOC.lat, step: 0.001 },
    { key: "lon", label: () => t("f_lon"), def: LOC.lon, step: 0.001 },
  ], async (v, btn) => {
    btn.disabled = true; busy(out);
    try {
      const d = await api.iono({ lat: v.lat, lon: v.lon }) as unknown as IonoRes;
      clear(out);
      const row = h("div", "exp-metrics");
      row.append(
        metric(t("m_peak"), d.peak[1].toFixed(2) + " m", "bad"),
        metric(t("m_night"), d.night.toFixed(2) + " m", "good"),
        metric(t("m_iffree"), d.if_residual.toFixed(3) + " m", "good"),
        metric(t("m_l1_20"), d.l1_at20.toFixed(2) + " m"),
      );
      out.appendChild(row);
      const leg = h("div", "legend"); leg.appendChild(legendChip(CHART_COLORS.cyan, t("iono_zenith")));
      const { card, canvas } = canvasCard(t("iono_diurnal"), leg);
      out.appendChild(card);
      requestAnimationFrame(() => drawLine(canvas,
        [{ label: "dz", color: CHART_COLORS.cyan, data: d.dz }],
        { x: d.hours, yMin: 0, xLabel: "h" }));
      const leg2 = h("div", "legend"); leg2.appendChild(legendChip(CHART_COLORS.amber, t("iono_slant")));
      const { card: c2, canvas: cv2 } = canvasCard(t("iono_by_elev"), leg2);
      out.appendChild(c2);
      requestAnimationFrame(() => drawLine(cv2,
        [{ label: "slant", color: CHART_COLORS.amber, data: d.slant }],
        { x: d.elevs, yMin: 0, xLabel: "° el" }));
    } catch (e) { fail(out, String(e)); } finally { btn.disabled = false; }
  }));
  root.appendChild(out);
}

// ---------- Scenariji ----------
const SCN_ROWS: Array<[string, (m: ScnMetrics) => string, "good" | "bad" | ""]> = [
  ["scn_median_err", (m) => fmtM(m.median_err), ""],
  ["scn_max_err", (m) => fmtM(m.max_err), ""],
  ["scn_gdop", (m) => (Number.isFinite(m.gdop_median) ? m.gdop_median.toFixed(2) : "—"), ""],
  ["scn_raim_alarms", (m) => String(m.raim_alarms), ""],
  ["scn_fix_lost", (m) => String(m.fix_lost), ""],
  ["scn_solved", (m) => `${m.solved}/${m.total}`, ""],
];
function fmtM(x: number): string {
  if (!Number.isFinite(x)) return "—";
  return x < 1000 ? x.toFixed(1) + " m" : (x / 1000).toFixed(2) + " km";
}

function scenarioPanel(root: HTMLElement): void {
  root.appendChild(eduCard("scenarios"));
  const bar = h("div", "exp-form");
  const selCell = h("div", "exp-field exp-field-wide");
  selCell.appendChild(h("label", "exp-flabel", t("scenarios")));
  const sel = h("select", "exp-select") as HTMLSelectElement;
  selCell.appendChild(sel);
  bar.appendChild(selCell);
  const runBtn = h("button", "btn primary exp-run", t("scenario_run")) as HTMLButtonElement;
  const cmpBtn = h("button", "btn exp-run", t("scenario_compare")) as HTMLButtonElement;
  const runCell = h("div", "exp-field exp-run-cell");
  runCell.append(runBtn, cmpBtn);
  bar.appendChild(runCell);
  const desc = h("div", "exp-note");
  const out = h("div", "exp-out");
  root.append(bar, desc, out);

  let metas: ScnMeta[] = [];
  function showDesc(): void {
    const m = metas.find((x) => x.file === sel.value);
    desc.textContent = m ? `${m.name} — ${m.description}` : "";
  }
  sel.addEventListener("change", showDesc);

  api.scenarioList().then((r) => {
    metas = r.scenarios as ScnMeta[];
    for (const m of metas) {
      const o = h("option", undefined, m.name + (m.attack ? ` · ${m.attack}` : "")) as HTMLOptionElement;
      o.value = m.file; sel.appendChild(o);
    }
    showDesc();
  }).catch((e) => fail(out, String(e)));

  function metricsTable(cols: Array<{ label: string; m: ScnMetrics }>): HTMLElement {
    const tbl = h("table", "exp-table scn-table");
    const hr = h("tr");
    hr.appendChild(h("th", undefined, t("scn_col_metric")));
    for (const c of cols) hr.appendChild(h("th", undefined, c.label));
    tbl.appendChild(hr);
    for (const [key, fn] of SCN_ROWS) {
      const tr = h("tr");
      tr.appendChild(h("td", undefined, t(key)));
      for (const c of cols) tr.appendChild(h("td", "mono", fn(c.m)));
      tbl.appendChild(tr);
    }
    // istaknuti redak "udaljenost od cilja" ako je koordinirani spoof
    if (cols.some((c) => c.m.takeover_m != null)) {
      const tr = h("tr");
      tr.appendChild(h("td", undefined, t("scn_takeover")));
      for (const c of cols) tr.appendChild(h("td", "mono", c.m.takeover_m != null ? fmtM(c.m.takeover_m) : "—"));
      tbl.appendChild(tr);
    }
    return tbl;
  }

  runBtn.addEventListener("click", async () => {
    if (!sel.value) return;
    runBtn.disabled = true; cmpBtn.disabled = true; busy(out);
    try {
      const d = await api.scenarioRun({ file: sel.value }) as unknown as ScnRun;
      clear(out);
      out.appendChild(metricsTable([{ label: t("scn_with_raim"), m: d.result }]));
    } catch (e) { fail(out, String(e)); } finally { runBtn.disabled = false; cmpBtn.disabled = false; }
  });

  cmpBtn.addEventListener("click", async () => {
    if (!sel.value) return;
    runBtn.disabled = true; cmpBtn.disabled = true; busy(out);
    try {
      const d = await api.scenarioCompare({ file: sel.value }) as unknown as ScnCompare;
      clear(out);
      out.appendChild(metricsTable([
        { label: t("scn_with_raim"), m: d.a.result },
        { label: t("scn_no_raim"), m: d.b.result },
      ]));
    } catch (e) { fail(out, String(e)); } finally { runBtn.disabled = false; cmpBtn.disabled = false; }
  });
}
