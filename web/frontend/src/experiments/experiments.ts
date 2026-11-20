// Panel eksperimenata (Faza 2): RTK, spoofing/jamming, multi-GNSS, ionosfera.
// Forma -> REST (/api/*) -> rezultat (brojke + grafovi) + edukativna kartica
// fizike. Sve crtanje ide kroz canvas primitive iz ui/charts.
import { h, clear } from "../lib/dom";
import { t, getLang, onLangChange, type Lang } from "../lib/i18n";
import { api } from "../lib/api";
import { drawLine, legendChip, CHART_COLORS, drawCiChart, EXTRA_COLORS, type CiSeries } from "../ui/charts";
import type { SandboxAggRow, SandboxExample, SandboxJob, SandboxResult } from "../lib/types";

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
interface RdSummary { n: number; h_median?: number; h_p95?: number; v_median?: number; v_p95?: number; d3_rms?: number; mean_enu?: [number, number, number]; }
interface RdRes { ok: boolean; station: string; receiver: string; start: string; solver: string; mask_deg: number; t: number[]; h_err: Array<number | null>; v_err: Array<number | null>; ls_h_err: Array<number | null>; nsat: number[]; gdop: Array<number | null>; raim_alarms: Array<[number, string]>; summary: RdSummary; ls_summary: RdSummary; n_epochs: number; solved: number; source: string; }

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
  sandbox: {
    hr: "Istraživački sandbox vrti CIJELU studiju iz jednog JSON speca: rešetku parametara (sweep) × Monte Carlo preko sjemena × više algoritama na ISTIM mjerenjima. Za svaku točku sweepa računa srednju vrijednost, medijan, p95 i 95 % interval pouzdanosti preko sjemena — pa vidiš je li razlika stvarna ili šum. Ključna metrika integriteta je 'misleading information' (greška > HPL bez alarma): RAIM je tu da se to nikad ne dogodi. Job radi u pozadini; rezultat se može preuzeti kao CSV.",
    en: "The research sandbox runs a WHOLE study from one JSON spec: a parameter grid (sweep) × Monte Carlo over seeds × several algorithms on the SAME measurements. For every sweep point it reports the mean, median, p95 and a 95 % confidence interval across seeds — so you can tell whether a difference is real or noise. The key integrity metric is 'misleading information' (error > HPL with no alarm): RAIM exists so that this never happens. The job runs in the background; results can be downloaded as CSV.",
  },
  realdata: {
    hr: "Ovdje nema simulacije: pseudoudaljenosti su STVARNA mjerenja geodetskog prijemnika (GEONET stanica 0759, Japan, 2. 4. 2005., 1 h @ 30 s, RINEX), a pozicije satelita računaju se iz emitiranih efemerida (IS-GPS-200: Kepler + harmonijske korekcije + rotacija Zemlje). Korigira se sat satelita (af0/af1/af2 + relativnost, TGD), ionosfera (Klobuchar s koeficijentima iz navigacijske poruke) i troposfera (Saastamoinen). Mjerenja ulaze u ISTI EKF/RAIM kao simulacija. Greška je razlika od poznate koordinate stanice — jednofrekvencijski SPP tipično daje nekoliko metara; ovaj prijemnik i mirna ionosfera daju i bolje.",
    en: "No simulation here: the pseudoranges are REAL measurements from a geodetic receiver (GEONET station 0759, Japan, 2 Apr 2005, 1 h @ 30 s, RINEX), and satellite positions come from the broadcast ephemerides (IS-GPS-200: Kepler + harmonic corrections + Earth rotation). The satellite clock (af0/af1/af2 + relativity, TGD), ionosphere (Klobuchar with coefficients from the navigation message) and troposphere (Saastamoinen) are corrected. The measurements feed the SAME EKF/RAIM as the simulation. The error is the offset from the station's known coordinate — single-frequency SPP is typically a few metres; this receiver and a quiet ionosphere do better.",
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
    { id: "realdata", title: () => t("exp_realdata"), body: realDataPanel },
    { id: "sandbox", title: () => t("exp_sandbox"), body: sandboxPanel },
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

// ---------- Pravi podaci (RINEX) ----------
function realDataPanel(root: HTMLElement): void {
  root.appendChild(eduCard("realdata"));
  const solverSel = h("select", "exp-select") as HTMLSelectElement;
  for (const [val, key] of [["ekf", "rd_solver_ekf"], ["ls", "rd_solver_ls"]] as const) {
    const o = h("option", undefined, t(key)) as HTMLOptionElement; o.value = val; solverSel.appendChild(o);
  }
  const selCell = h("div", "exp-field");
  selCell.appendChild(h("label", "exp-flabel", t("rd_solver")));
  selCell.appendChild(solverSel);

  const out = h("div", "exp-out");
  const f = form([
    { key: "mask_deg", label: () => t("f_mask"), def: 10, min: 0, max: 40 },
  ], async (v, btn) => {
    btn.disabled = true; busy(out);
    try {
      const d = await api.realdata({ mask_deg: v.mask_deg, solver: solverSel.value }) as unknown as RdRes;
      clear(out);
      if (!d.ok) { fail(out, "—"); return; }
      const s = d.summary;
      const m = (x?: number) => (x != null && Number.isFinite(x) ? x.toFixed(2) + " m" : "—");
      const row = h("div", "exp-metrics");
      row.append(
        metric(t("rd_h_med"), m(s.h_median), "good"),
        metric(t("rd_h_p95"), m(s.h_p95)),
        metric(t("rd_v_med"), m(s.v_median)),
        metric(t("rd_v_p95"), m(s.v_p95)),
        metric(t("rd_epochs"), `${d.solved}/${d.n_epochs}`),
        metric(t("m_alarms"), String(d.raim_alarms.length), d.raim_alarms.length ? "bad" : ""),
      );
      out.appendChild(row);
      const enu = s.mean_enu ? s.mean_enu.map((x) => (x >= 0 ? "+" : "") + x.toFixed(2)).join(" / ") + " m" : "—";
      out.appendChild(h("div", "exp-note",
        `${t("rd_station")}: ${d.station} (${d.receiver}) · ${d.start} GPST · ${t("rd_mean_enu")}: ${enu}`));
      const xs = d.t.map((x) => x / 60);
      const leg = h("div", "legend");
      leg.append(legendChip(CHART_COLORS.cyan, t("rd_h")), legendChip(CHART_COLORS.amber, t("rd_v")),
        legendChip(CHART_COLORS.dim, t("rd_ls")));
      const { card, canvas } = canvasCard(t("rd_err_chart"), leg);
      out.appendChild(card);
      requestAnimationFrame(() => drawLine(canvas, [
        { label: "ls", color: CHART_COLORS.dim, data: d.ls_h_err },
        { label: "h", color: CHART_COLORS.cyan, data: d.h_err },
        { label: "v", color: CHART_COLORS.amber, data: d.v_err },
      ], { x: xs, xLabel: "min", hlines: [{ y: 0, color: CHART_COLORS.dim, dash: true }] }));
      const leg2 = h("div", "legend");
      leg2.append(legendChip(CHART_COLORS.green, t("sats")), legendChip(CHART_COLORS.red, "GDOP"));
      const { card: c2, canvas: cv2 } = canvasCard(t("rd_sats_chart"), leg2);
      out.appendChild(c2);
      requestAnimationFrame(() => drawLine(cv2, [
        { label: "sats", color: CHART_COLORS.green, data: d.nsat },
        { label: "gdop", color: CHART_COLORS.red, data: d.gdop },
      ], { x: xs, yMin: 0, xLabel: "min" }));
      out.appendChild(h("div", "exp-note", `${t("rd_source")}: ${d.source}`));
    } catch (e) { fail(out, String(e)); } finally { btn.disabled = false; }
  });
  f.insertBefore(selCell, f.lastChild);
  root.append(f, out);
}

// ---------- Istraživački sandbox ----------
// Stanje živi izvan panela: prebacivanje kartica ili jezika ne gubi uređeni spec
// ni pokrenuti job (polling nastavlja i ponovno crta u trenutno montirani panel).
const SB = {
  text: "",
  example: "",
  job: null as SandboxJob | null,
  polling: false,
  metric: "",
  x: "",
  rerender: null as null | (() => void),
};

function sbFmt(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a !== 0 && (a < 0.001 || a >= 1e6)) return v.toExponential(2);
  if (a < 1) return v.toFixed(3);
  if (a < 100) return v.toFixed(2);
  return v.toFixed(0);
}
function sbLabel(v: unknown): string {
  if (Array.isArray(v)) return v.join("+");
  if (v != null && typeof v === "object") return JSON.stringify(v);
  return String(v);
}
function tpl(s: string, vals: Record<string, string | number>): string {
  return s.replace(/\{(\w+)\}/g, (_, k) => String(vals[k] ?? ""));
}

async function sbPoll(): Promise<void> {
  if (SB.polling || !SB.job) return;
  SB.polling = true;
  try {
    while (SB.job && (SB.job.status === "queued" || SB.job.status === "running")) {
      await new Promise((r) => setTimeout(r, 1000));
      try { SB.job = await api.sandboxJob(SB.job.id); } catch { /* prolazna greška mreže */ }
      SB.rerender?.();
    }
  } finally { SB.polling = false; }
}

function sandboxPanel(root: HTMLElement): void {
  root.appendChild(eduCard("sandbox"));
  const bar = h("div", "exp-form");
  const selCell = h("div", "exp-field exp-field-wide");
  selCell.appendChild(h("label", "exp-flabel", t("sb_example")));
  const sel = h("select", "exp-select") as HTMLSelectElement;
  selCell.appendChild(sel);
  bar.appendChild(selCell);
  const valBtn = h("button", "btn exp-run", t("sb_validate")) as HTMLButtonElement;
  const runBtn = h("button", "btn primary exp-run", t("sb_run")) as HTMLButtonElement;
  const cancelBtn = h("button", "btn exp-run", t("sb_cancel")) as HTMLButtonElement;
  const runCell = h("div", "exp-field exp-run-cell sb-btns");
  runCell.append(valBtn, runBtn, cancelBtn);
  bar.appendChild(runCell);
  const desc = h("div", "exp-note");
  const specLabel = h("label", "exp-flabel", t("sb_spec"));
  const ta = h("textarea", "sb-spec") as HTMLTextAreaElement;
  ta.spellcheck = false;
  ta.value = SB.text;
  const msg = h("div", "sb-msg");
  const limits = h("div", "exp-note sb-hint");
  const status = h("div", "sb-status");
  const out = h("div", "exp-out");
  root.append(bar, desc, specLabel, ta, msg, limits, status, out);

  let examples: SandboxExample[] = [];
  ta.addEventListener("input", () => { SB.text = ta.value; });

  function showExample(file: string, fill: boolean): void {
    const ex = examples.find((e) => e.file === file);
    SB.example = file;
    desc.textContent = ex ? `${ex.name} — ${ex.description}` : "";
    if (ex && fill) { ta.value = JSON.stringify(ex.spec, null, 2); SB.text = ta.value; clear(msg); }
  }
  sel.addEventListener("change", () => showExample(sel.value, true));

  api.sandboxExamples().then((r) => {
    examples = r.examples;
    for (const e of examples) {
      const o = h("option", undefined, e.name + (e.size ? ` · ${e.size.runs} runs` : "")) as HTMLOptionElement;
      o.value = e.file; sel.appendChild(o);
    }
    if (SB.example && examples.some((e) => e.file === SB.example)) sel.value = SB.example;
    showExample(sel.value, !SB.text);
    limits.textContent = tpl(t("sb_limits"), { r: r.limits.max_runs, e: r.limits.max_epochs }) + " " + t("sb_cli_hint");
  }).catch((e) => fail(out, String(e)));

  function parse(): unknown | null {
    try { return JSON.parse(ta.value); } catch (e) {
      showErrors(t("sb_json_err"), [String((e as Error).message)]);
      return null;
    }
  }
  function showErrors(head: string, errs: string[]): void {
    clear(msg); msg.className = "sb-msg bad";
    msg.appendChild(h("div", undefined, head));
    const ul = h("ul");
    for (const e of errs) ul.appendChild(h("li", "mono", e));
    msg.appendChild(ul);
  }
  function showOk(size: { points: number; locations: number; seeds: number; runs: number; epochs: number }): void {
    clear(msg); msg.className = "sb-msg good";
    msg.textContent = tpl(t("sb_valid"), { p: size.points, l: size.locations, s: size.seeds, r: size.runs, e: size.epochs });
  }

  valBtn.addEventListener("click", async () => {
    const spec = parse(); if (spec == null) return;
    try {
      const r = await api.sandboxValidate(spec);
      if (r.ok && r.size) showOk(r.size); else showErrors(t("sb_invalid"), r.errors);
    } catch (e) { showErrors(t("sb_invalid"), [String(e)]); }
  });

  runBtn.addEventListener("click", async () => {
    const spec = parse(); if (spec == null) return;
    runBtn.disabled = true;
    try {
      const r = await api.sandboxRun(spec);
      if (r.status === 429) { showErrors(t("sb_busy"), []); return; }
      if (!r.ok || !r.body.job_id) {
        const det = r.body?.detail as { errors?: string[] } | string | undefined;
        const errs = typeof det === "string" ? [det] : det?.errors ?? [JSON.stringify(r.body)];
        showErrors(t("sb_invalid"), errs);
        return;
      }
      if (r.body.size) showOk(r.body.size);
      SB.metric = ""; SB.x = "";
      SB.job = { id: r.body.job_id, status: "queued", done: 0, total: r.body.size?.runs ?? 0, error: null,
        name: "", created: Date.now() / 1000, started: null, finished: null };
      renderJob();
      void sbPoll();
    } catch (e) { showErrors(t("sb_invalid"), [String(e)]); } finally { runBtn.disabled = false; renderButtons(); }
  });

  cancelBtn.addEventListener("click", async () => {
    if (!SB.job) return;
    try { await api.sandboxCancel(SB.job.id); } catch { /* ignore */ }
  });

  function renderButtons(): void {
    const busyJob = !!SB.job && (SB.job.status === "queued" || SB.job.status === "running");
    runBtn.disabled = busyJob;
    cancelBtn.style.display = busyJob ? "" : "none";
  }

  let shownResultFor = "";
  function renderJob(): void {
    renderButtons();
    clear(status);
    const job = SB.job;
    if (!job) return;
    const pct = job.total ? Math.round((100 * job.done) / job.total) : 0;
    const line = h("div", "sb-status-line");
    line.appendChild(h("span", "sb-badge sb-" + job.status, t("sb_status_" + job.status)));
    line.appendChild(h("span", "mono", tpl(t("sb_runs_done"), { d: job.done, t: job.total })));
    status.appendChild(line);
    const prog = h("div", "sb-progress");
    const fill = h("div", "sb-progress-fill");
    fill.style.width = pct + "%";
    prog.appendChild(fill);
    status.appendChild(prog);
    if (job.status === "error") { fail(out, job.error ?? "error"); shownResultFor = ""; return; }
    if (job.result && shownResultFor !== job.id + job.status) {
      shownResultFor = job.id + job.status;
      renderResult(job.id, job.result);
    } else if (!job.result) { clear(out); shownResultFor = ""; }
  }

  function renderResult(jobId: string, res: SandboxResult): void {
    clear(out);
    const metrics = (res.spec.metrics ?? []) as string[];
    const sweepKeys = Object.keys(res.spec.sweep ?? {});
    const multiLoc = new Set(res.aggregate.map((a) => a.location)).size > 1;
    const xs = [...sweepKeys, ...(multiLoc ? ["location"] : [])];
    if (!metrics.includes(SB.metric)) SB.metric = metrics[0] ?? "";
    if (!xs.includes(SB.x)) SB.x = xs[0] ?? "";

    const ctl = h("div", "exp-form");
    const mk = (labelKey: string, opts: string[], cur: string, on: (v: string) => void) => {
      const cell = h("div", "exp-field");
      cell.appendChild(h("label", "exp-flabel", t(labelKey)));
      const s = h("select", "exp-select sb-select") as HTMLSelectElement;
      for (const o of opts) { const op = h("option", undefined, o) as HTMLOptionElement; op.value = o; s.appendChild(op); }
      s.value = cur;
      s.addEventListener("change", () => { on(s.value); draw(); });
      cell.appendChild(s);
      return cell;
    };
    ctl.appendChild(mk("sb_metric", metrics, SB.metric, (v) => { SB.metric = v; }));
    if (xs.length) ctl.appendChild(mk("sb_xparam", xs, SB.x, (v) => { SB.x = v; }));
    const dl = h("div", "exp-field exp-run-cell sb-btns");
    for (const [kind, key] of [["aggregate", "sb_csv"], ["runs", "sb_csv_runs"]] as const) {
      const a = h("a", "btn exp-run", "⬇ " + t(key)) as HTMLAnchorElement;
      a.href = api.sandboxCsvUrl(jobId, kind);
      a.setAttribute("download", "");
      dl.appendChild(a);
    }
    ctl.appendChild(dl);
    out.appendChild(ctl);

    const meta = res.meta;
    const git = meta.git ? `${t("sb_commit")} ${meta.git.commit.slice(0, 8)}${meta.git.dirty ? "+" : ""}` : "";
    out.appendChild(h("div", "exp-note",
      `${res.spec.name ?? ""} · ${t("sb_elapsed")}: ${sbFmt(meta.elapsed_s ?? null)} s · ${meta.runs_done}/${meta.runs_total} · ${git}`));

    const chartHost = h("div");
    const tableHost = h("div");
    out.append(chartHost, h("div", "exp-note", t("sb_ci_note")), tableHost);

    function draw(): void {
      clear(chartHost); clear(tableHost);
      const metric = SB.metric, x = SB.x;
      const xval = (a: SandboxAggRow): unknown => (x === "location" ? a.location : x ? a.params[x] : 0);
      const numeric = !!x && res.aggregate.every((a) => typeof xval(a) === "number");
      const cats: string[] = [];
      if (!numeric) for (const a of res.aggregate) { const l = sbLabel(xval(a)); if (!cats.includes(l)) cats.push(l); }
      const nEst = new Set(res.aggregate.map((a) => a.estimator)).size;
      const groups = new Map<string, SandboxAggRow[]>();
      for (const a of res.aggregate) {
        const parts = sweepKeys.filter((k) => k !== x).map((k) => `${k.split(".").pop()}=${sbLabel(a.params[k])}`);
        if (multiLoc && x !== "location") parts.push(a.location);
        if (nEst > 1 || !parts.length) parts.push(a.estimator);
        const key = parts.join(", ");
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key)!.push(a);
      }
      const colors = [CHART_COLORS.cyan, CHART_COLORS.amber, CHART_COLORS.green, CHART_COLORS.red, ...EXTRA_COLORS, CHART_COLORS.dim];
      const series: CiSeries[] = [];
      const leg = h("div", "legend");
      let gi = 0;
      for (const [label, rows] of groups) {
        const color = colors[gi++ % colors.length];
        series.push({
          label, color,
          x: rows.map((a) => (numeric ? (xval(a) as number) : cats.indexOf(sbLabel(xval(a))))),
          mean: rows.map((a) => a.metrics[metric]?.mean ?? null),
          lo: rows.map((a) => a.metrics[metric]?.ci_lo ?? null),
          hi: rows.map((a) => a.metrics[metric]?.ci_hi ?? null),
        });
        leg.appendChild(legendChip(color, label));
      }
      const xsNum = numeric ? res.aggregate.map((a) => xval(a) as number) : [];
      const pos = xsNum.filter((v) => v > 0);
      const logX = numeric && pos.length === xsNum.length && pos.length > 1
        && (/(pfa|pmd)$/.test(x) || Math.max(...pos) / Math.min(...pos) >= 1000);
      const { card, canvas } = canvasCard(`${metric}${x ? " vs " + x : ""}`, leg);
      canvas.classList.add("sb-canvas");
      chartHost.appendChild(card);
      requestAnimationFrame(() => drawCiChart(canvas, series, { xLabels: numeric ? undefined : cats, logX }));

      // tablica: parametri, estimator, srednja, CI, n
      const tbl = h("table", "exp-table sb-table");
      const hr = h("tr");
      for (const c of [...sweepKeys, ...(multiLoc ? ["location"] : []), t("sb_estimator"), t("sb_col_mean"), t("sb_col_ci"), t("sb_col_n")]) {
        hr.appendChild(h("th", undefined, c));
      }
      tbl.appendChild(hr);
      for (const a of res.aggregate) {
        const s = a.metrics[metric];
        const tr = h("tr");
        for (const k of sweepKeys) tr.appendChild(h("td", "mono", sbLabel(a.params[k])));
        if (multiLoc) tr.appendChild(h("td", "mono", a.location));
        tr.appendChild(h("td", "mono", a.estimator));
        tr.appendChild(h("td", "mono", sbFmt(s?.mean)));
        tr.appendChild(h("td", "mono", s && s.ci_lo != null ? `[${sbFmt(s.ci_lo)}, ${sbFmt(s.ci_hi)}]` : "—"));
        tr.appendChild(h("td", "mono", String(s?.n ?? 0)));
        tbl.appendChild(tr);
      }
      const wrap = h("div", "exp-chart-card sb-table-wrap");
      wrap.appendChild(tbl);
      tableHost.appendChild(wrap);
    }
    draw();
  }

  SB.rerender = () => { if (root.isConnected) renderJob(); };
  renderJob();
  if (SB.job && (SB.job.status === "queued" || SB.job.status === "running")) void sbPoll();
}
