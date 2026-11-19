// "Pogled iznutra" — međuveličine JEDNE epohe navigacijskog rješenja.
// Četiri kartice prate put od mjerenja do pozicije:
//   1. Mjerenja   — od čega se sastoji pseudoudaljenost i inovacija (+ proračun greške
//                   koji zna samo simulator)
//   2. Geometrija — matrica G i DOP-ovi: zašto raspored satelita množi grešku
//   3. Kalmanov korak — predikcija → inovacija → pojačanje → ažuriranje (ENU, prema istini)
//   4. RAIM       — testna statistika na krivulji χ², normalizirani reziduali, nagibi i HPL
// Podaci: GET /api/inspect (web/backend/inspect_epoch.py). Gumbi: zamrzni (pauza),
// korak (+1 s) i automatsko osvježavanje.
import { h, clear, term } from "../lib/dom";
import { getLang, onLangChange, type Lang } from "../lib/i18n";
import { drawLine } from "../ui/charts";

type Send = (msg: Record<string, unknown>) => void;
type Num = number | null;

interface MeasInfo {
  id: string; system: string; az: Num; el: Num; used: boolean; excluded: boolean;
  pseudorange: Num; true_range: Num;
  model: { geometric: Num; clock: Num; sagnac: Num; isb: Num; predicted: Num };
  innovation: Num; sigma: Num;
  error_budget: Record<string, Num>; error_total: Num; ephemeris_los: Num;
  los_enu: Num[]; gain_enu?: Num[]; contribution_enu?: Num[];
}
interface Inspect {
  available: boolean; reason?: string; sim_time: number; error_m: Num;
  measurements: MeasInfo[];
  geometry: { columns: string[]; rows: Array<{ id: string; g: Num[] }>; dop: Record<string, Num> | null; Q: Num[][] | null; n: number; m: number };
  kalman: {
    dt: Num; t: Num;
    before: { enu: Num[]; clock_m: Num };
    predicted: { enu: Num[]; clock_m: Num; std_enu: Num[]; clock_std: Num };
    updated: { enu: Num[]; clock_m: Num; std_enu: Num[]; clock_std: Num };
    correction_enu: Num[]; clock_correction_m: Num; velocity_enu: Num[];
    nis: Num; nis_dof: number; true_clock_m: Num;
  };
  raim: {
    integrity: Record<string, unknown>;
    test?: Num; threshold?: Num; dof?: number; lambda?: Num; pbias?: Num; pfa?: number; pmd?: number;
    pdf_x?: number[]; pdf_y?: number[];
    sats?: Array<{ id: string; residual: Num; normalized: Num; sigma: Num; hslope: Num; vslope: Num }>;
  };
}

// ---- tekstovi (dvojezično, lokalno radi preglednosti) ----------------------
const TX: Record<string, Record<Lang, string>> = {
  title: { hr: "Pogled iznutra — jedna epoha", en: "Inside view — one epoch" },
  refresh: { hr: "Osvježi", en: "Refresh" },
  freeze: { hr: "Zamrzni (pauza)", en: "Freeze (pause)" },
  step: { hr: "Korak +1 s", en: "Step +1 s" },
  auto: { hr: "auto-osvježavanje", en: "auto-refresh" },
  tab_meas: { hr: "1. Mjerenja", en: "1. Measurements" },
  tab_geom: { hr: "2. Geometrija", en: "2. Geometry" },
  tab_kal: { hr: "3. Kalmanov korak", en: "3. Kalman step" },
  tab_raim: { hr: "4. RAIM", en: "4. RAIM" },
  no_receiver: { hr: "Prijemnik nije postavljen — dvoklikni na globus.", en: "No receiver placed — double-click the globe." },
  no_solution: { hr: "Još nema rješenja — pokreni simulaciju (ili klikni Korak).", en: "No solution yet — start the simulation (or click Step)." },
  status: { hr: "epoha t = {t} s · greška procjene {e} m", en: "epoch t = {t} s · estimate error {e} m" },
  intro_meas: {
    hr: "Prijemnik ne mjeri udaljenost nego PSEUDOudaljenost: vrijeme leta signala × c, uključujući pomak vlastitog sata. Za svaki satelit filtar PREDVIDI koliko bi ona trebala iznositi (geometrijska udaljenost do objavljene pozicije satelita + sat prijemnika + Sagnac + ISB). Razlika izmjereno − predviđeno je INOVACIJA — jedina nova informacija koju epoha donosi. Klikni redak za detalje.",
    en: "A receiver does not measure range but PSEUDOrange: signal flight time × c, including its own clock offset. For each satellite the filter PREDICTS what it should be (geometric range to the broadcast satellite position + receiver clock + Sagnac + ISB). Measured − predicted is the INNOVATION — the only new information an epoch brings. Click a row for details.",
  },
  budget_title: { hr: "Proračun greške mjerenja (zna samo simulator)", en: "Measurement error budget (only the simulator knows)" },
  budget_note: {
    hr: "Pseudoudaljenost − prava udaljenost. Sat prijemnika je ogroman, ali isti za sve satelite pa ga filtar procijeni kao 4. nepoznanicu. Sagnac i ISB su poznati modeli. Ono što preostane (multipath, šum pojačan iono-free kombinacijom, eventualni napad) je prava greška koju geometrija prenosi na poziciju.",
    en: "Pseudorange − true range. The receiver clock is huge but common to all satellites, so the filter estimates it as the 4th unknown. Sagnac and ISB are known models. What remains (multipath, noise amplified by the iono-free combination, any attack) is the real error that geometry maps into position.",
  },
  model_title: { hr: "Model pseudoudaljenosti (što prijemnik predviđa)", en: "Pseudorange model (what the receiver predicts)" },
  eph_note: {
    hr: "Greška efemerida (objavljena − stvarna pozicija satelita, duž linije pogleda) ne ulazi u mjerenje nego u MODEL — prijemnik računa udaljenost do pozicije iz navigacijske poruke.",
    en: "The ephemeris error (broadcast − true satellite position, along the line of sight) does not enter the measurement but the MODEL — the receiver computes range to the position from the navigation message.",
  },
  intro_geom: {
    hr: "Svaki redak matrice geometrije G je jedinični vektor od satelita prema prijemniku (istok, sjever, gore) plus 1 za sat (po sustavu). Rješenje je δx = (GᵀWG)⁻¹GᵀW·y, pa dijagonala (GᵀG)⁻¹ govori koliko se 1 m greške mjerenja pretvara u grešku pozicije — to su DOP-ovi. Sateliti raspršeni po nebu → mali DOP; zbijeni → veliki. VDOP je redovito veći od HDOP-a jer su svi sateliti IZNAD nas.",
    en: "Each row of the geometry matrix G is the unit vector from satellite to receiver (east, north, up) plus 1 for the clock (per system). The solution is δx = (GᵀWG)⁻¹GᵀW·y, so the diagonal of (GᵀG)⁻¹ tells how 1 m of measurement error becomes position error — those are the DOPs. Satellites spread across the sky → small DOP; clustered → large. VDOP is usually larger than HDOP because all satellites are ABOVE us.",
  },
  intro_kal: {
    hr: "Kalmanov filtar radi u dva koraka. PREDIKCIJA: pomakni stanje modelom gibanja (pozicija += brzina·dt, sat += drift·dt) i povećaj nesigurnost P za procesni šum. AŽURIRANJE: pojačanje K = P·Hᵀ·S⁻¹ odluči koliko vjerovati inovacijama u odnosu na predikciju; nova procjena = predikcija + K·inovacija, a nesigurnost se smanji. Sve greške su ENU (istok/sjever/gore) u metrima prema PRAVOJ poziciji.",
    en: "The Kalman filter works in two steps. PREDICT: move the state with the motion model (position += velocity·dt, clock += drift·dt) and grow the uncertainty P by process noise. UPDATE: the gain K = P·Hᵀ·S⁻¹ decides how much to trust the innovations versus the prediction; new estimate = prediction + K·innovation, and the uncertainty shrinks. All errors are ENU (east/north/up) in metres relative to the TRUE position.",
  },
  intro_raim: {
    hr: "RAIM provjerava jesu li mjerenja međusobno dosljedna. Iz VIŠKA satelita (više nego nepoznanica) težinski najmanji kvadrati ostave rezidual; suma kvadrata normaliziranih reziduala T ima χ² razdiobu ako nema kvara. Prag T_d je odabran tako da lažni alarm bude rijedak (P_FA). Nagib (slope) satelita kaže koliko bi njegov neotkriveni kvar pomaknuo poziciju po jedinici testne statistike; HPL = najveći nagib × √λ.",
    en: "RAIM checks whether the measurements agree with each other. With SURPLUS satellites (more than unknowns), weighted least squares leaves a residual; the sum of squared normalized residuals T is χ²-distributed when there is no fault. The threshold T_d is chosen so false alarms are rare (P_FA). A satellite's slope says how far its undetected fault would move the position per unit of test statistic; HPL = largest slope × √λ.",
  },
};
const tx = (k: string): string => TX[k][getLang()];

const fmt = (v: Num | undefined, d = 2): string => (v == null ? "—" : v.toFixed(d));
const fmtSigned = (v: Num | undefined, d = 2): string => (v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(d));

const BUDGET_LABEL: Record<string, Record<Lang, string>> = {
  rx_clock: { hr: "sat prijemnika", en: "receiver clock" },
  sagnac: { hr: "Sagnac (rotacija Zemlje)", en: "Sagnac (Earth rotation)" },
  isb: { hr: "ISB (vremenska skala sustava)", en: "ISB (system time scale)" },
  sat_fault: { hr: "kvar sata satelita (ubrizgan)", en: "satellite clock fault (injected)" },
  tropo_resid: { hr: "troposfera (ostatak korekcije)", en: "troposphere (correction residual)" },
  remainder: { hr: "multipath + šum + napad", en: "multipath + noise + attack" },
};

export function mountInside(send: Send) {
  let data: Inspect | null = null;
  let tab = "meas";
  let selected: string | null = null;
  let timer: number | null = null;

  const overlay = h("div", "modal-overlay");
  overlay.style.display = "none";
  const modal = h("div", "modal inside-modal");
  const head = h("div", "modal-head");
  const title = h("div", "modal-title");
  const close = h("button", "modal-close", "×");
  head.append(title, close);

  const bar = h("div", "inside-bar");
  const btnRefresh = h("button", "btn");
  const btnFreeze = h("button", "btn");
  const btnStep = h("button", "btn primary");
  const autoLbl = h("label", "inside-auto");
  const autoChk = document.createElement("input");
  autoChk.type = "checkbox"; autoChk.checked = true;
  const autoTxt = h("span");
  autoLbl.append(autoChk, autoTxt);
  const status = h("div", "inside-status");
  bar.append(btnRefresh, btnFreeze, btnStep, autoLbl, status);

  const tabs = h("div", "modal-tabs");
  const content = h("div", "modal-content inside-content");
  modal.append(head, bar, tabs, content);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  overlay.addEventListener("click", (e) => { if (e.target === overlay) hide(); });
  close.addEventListener("click", hide);
  btnRefresh.addEventListener("click", () => void load());
  btnFreeze.addEventListener("click", () => { send({ type: "pause" }); autoChk.checked = false; setAuto(); void load(); });
  btnStep.addEventListener("click", () => {
    send({ type: "pause" });
    send({ type: "step", sim_dt: 1.0 });
    autoChk.checked = false; setAuto();
    window.setTimeout(() => void load(), 350);
  });
  autoChk.addEventListener("change", setAuto);

  function setAuto(): void {
    if (timer != null) { window.clearInterval(timer); timer = null; }
    if (autoChk.checked && overlay.style.display !== "none") timer = window.setInterval(() => void load(), 1500);
  }

  async function load(): Promise<void> {
    try {
      const r = await fetch("/api/inspect");
      if (!r.ok) throw new Error(String(r.status));
      data = (await r.json()) as Inspect;
    } catch { data = null; }
    render();
  }

  function renderChrome(): void {
    title.textContent = tx("title");
    btnRefresh.textContent = tx("refresh");
    btnFreeze.textContent = tx("freeze");
    btnStep.textContent = tx("step");
    autoTxt.textContent = " " + tx("auto");
    const defs: Array<[string, string]> = [["meas", "tab_meas"], ["geom", "tab_geom"], ["kal", "tab_kal"], ["raim", "tab_raim"]];
    tabs.replaceChildren(...defs.map(([id, key]) => {
      const b = h("button", "modal-tab" + (tab === id ? " active" : ""), tx(key));
      b.addEventListener("click", () => { tab = id; render(); });
      return b;
    }));
  }

  function para(key: string): HTMLElement { return h("p", "inside-intro", tx(key)); }

  function table(headers: string[], rows: Array<Array<string | HTMLElement>>, cls = ""): HTMLElement {
    const t = h("table", "inside-table " + cls);
    const hr = h("tr");
    headers.forEach((x) => hr.appendChild(h("th", undefined, x)));
    t.appendChild(hr);
    for (const r of rows) {
      const tr = h("tr");
      r.forEach((c) => { const td = h("td"); if (typeof c === "string") td.textContent = c; else td.appendChild(c); tr.appendChild(td); });
      t.appendChild(tr);
    }
    return t;
  }

  // Vodoravna traka (vrijednost / max) s predznakom: lijevo negativno, desno pozitivno.
  function bar1(v: Num, max: number, color = "var(--cyan)"): HTMLElement {
    const wrap = h("div", "inside-barwrap");
    const b = h("div", "inside-bar1");
    const frac = v == null || max <= 0 ? 0 : Math.min(1, Math.abs(v) / max);
    b.style.width = `${(frac * 50).toFixed(1)}%`;
    b.style.background = color;
    if ((v ?? 0) < 0) { b.style.right = "50%"; } else { b.style.left = "50%"; }
    wrap.append(h("div", "inside-axis"), b);
    return wrap;
  }

  // ---- 1. mjerenja ------------------------------------------------------
  function renderMeas(d: Inspect): void {
    content.appendChild(para("intro_meas"));
    const ms = [...d.measurements].sort((a, b) => (b.el ?? 0) - (a.el ?? 0));
    if (!selected || !ms.find((m) => m.id === selected)) selected = ms[0]?.id ?? null;
    const maxInn = Math.max(1, ...ms.filter((m) => m.used).map((m) => Math.abs(m.innovation ?? 0)));
    const rows = ms.map((m) => {
      const id = h("span", "mono" + (m.id === selected ? " inside-sel" : ""), m.id);
      const st = m.excluded ? "✕" : m.used ? "●" : "○";
      return [id, m.system, fmt(m.el, 1) + "°", fmt(m.az, 0) + "°",
        fmtSigned(m.innovation), bar1(m.innovation, maxInn, m.excluded ? "var(--red)" : "var(--cyan)"),
        fmt(m.sigma), st];
    });
    const t = table(["sat", getLang() === "hr" ? "sustav" : "system", "el", "az",
      getLang() === "hr" ? "inovacija [m]" : "innovation [m]", "", "σ [m]", ""], rows, "clickable");
    Array.from(t.querySelectorAll("tr")).slice(1).forEach((tr, i) => {
      tr.addEventListener("click", () => { selected = ms[i].id; render(); });
    });
    content.appendChild(t);

    const m = ms.find((x) => x.id === selected);
    if (!m) return;
    const grid = h("div", "inside-grid2");
    // model
    const mod = h("div", "inside-card");
    mod.appendChild(h("div", "inside-card-title", `${tx("model_title")} — ${m.id}`));
    const mrows: Array<[string, string]> = [
      [getLang() === "hr" ? "geometrijska udaljenost (do objavljene pozicije)" : "geometric range (to broadcast position)", fmt(m.model.geometric, 3)],
      [getLang() === "hr" ? "+ sat prijemnika (c·b, procjena)" : "+ receiver clock (c·b, estimate)", fmtSigned(m.model.clock, 3)],
      ["+ Sagnac", fmtSigned(m.model.sagnac, 3)],
      ["+ ISB", fmtSigned(m.model.isb, 3)],
      [getLang() === "hr" ? "= predviđeno" : "= predicted", fmt(m.model.predicted, 3)],
      [getLang() === "hr" ? "izmjereno" : "measured", fmt(m.pseudorange, 3)],
      [getLang() === "hr" ? "inovacija = izmjereno − predviđeno" : "innovation = measured − predicted", fmtSigned(m.innovation, 3)],
    ];
    mod.appendChild(table(["", "m"], mrows.map(([a, b]) => [a, b]), "kv"));
    const eph = h("p", "inside-note", `${tx("eph_note")} (${fmtSigned(m.ephemeris_los)} m)`);
    mod.appendChild(eph);
    // proračun greške
    const bud = h("div", "inside-card");
    bud.appendChild(h("div", "inside-card-title", tx("budget_title")));
    const parts = Object.entries(m.error_budget);
    const small = parts.filter(([k]) => k !== "rx_clock").map(([, v]) => Math.abs(v ?? 0));
    const maxSmall = Math.max(1, ...small);
    bud.appendChild(table(["", "m", ""], parts.map(([k, v]) => [
      BUDGET_LABEL[k]?.[getLang()] ?? k, fmtSigned(v),
      k === "rx_clock" ? h("span", "inside-note", getLang() === "hr" ? "(zajednički — van skale)" : "(common — off scale)")
        : bar1(v, maxSmall, k === "remainder" ? "var(--amber)" : k === "sat_fault" ? "var(--red)" : "var(--cyan)"),
    ]).concat([[getLang() === "hr" ? "ukupno (pr − prava udaljenost)" : "total (pr − true range)", fmtSigned(m.error_total), ""]]), "kv"));
    bud.appendChild(h("p", "inside-note", tx("budget_note")));
    grid.append(mod, bud);
    content.appendChild(grid);
  }

  // ---- 2. geometrija ----------------------------------------------------
  function renderGeom(d: Inspect): void {
    content.appendChild(para("intro_geom"));
    const g = d.geometry;
    if (g.dop) {
      const tiles = h("div", "inside-tiles");
      for (const k of ["GDOP", "PDOP", "HDOP", "VDOP", "TDOP", "EDOP", "NDOP"]) {
        const tile = h("div", "inside-tile");
        tile.append(k === "GDOP" || k === "PDOP" ? term(k) : h("span", "inside-tile-k", k), h("div", "inside-tile-v", fmt(g.dop[k])));
        tiles.appendChild(tile);
      }
      content.appendChild(tiles);
    }
    content.appendChild(h("div", "inside-card-title",
      (getLang() === "hr" ? "Matrica geometrije G" : "Geometry matrix G") + ` (${g.n} × ${g.m})`));
    content.appendChild(table(["sat", ...g.columns], g.rows.map((r) => [r.id, ...r.g.map((v) => fmt(v, 3))]), "mono"));
    if (g.Q) {
      content.appendChild(h("div", "inside-card-title", "(GᵀG)⁻¹ — " + (getLang() === "hr" ? "dijagonala = kvadrati DOP-ova po osi (EDOP², NDOP², VDOP², TDOP²)" : "diagonal = squared DOP per axis (EDOP², NDOP², VDOP², TDOP²)")));
      content.appendChild(table(["", ...g.columns], g.Q.map((row, i) => [g.columns[i], ...row.map((v) => fmt(v, 3))]), "mono"));
    }
  }

  // ---- 3. Kalmanov korak ------------------------------------------------
  function renderKal(d: Inspect): void {
    content.appendChild(para("intro_kal"));
    const k = d.kalman;
    const hr = getLang() === "hr";
    const row = (label: string, e: Num[], s?: Num[]) => [label,
      ...e.map((v, i) => fmtSigned(v) + (s ? `  ±${fmt(s[i], 1)}` : "")), ""];
    content.appendChild(table(["", hr ? "istok" : "east", hr ? "sjever" : "north", hr ? "gore" : "up", ""], [
      row(hr ? "prije (prošla epoha)" : "before (last epoch)", k.before.enu),
      row(hr ? `predikcija (dt = ${fmt(k.dt, 1)} s)` : `prediction (dt = ${fmt(k.dt, 1)} s)`, k.predicted.enu, k.predicted.std_enu),
      row(hr ? "ažurirano" : "updated", k.updated.enu, k.updated.std_enu),
      row(hr ? "korekcija = K·inovacija" : "correction = K·innovation", k.correction_enu),
    ], "mono"));
    content.appendChild(h("p", "inside-note", hr
      ? `Greške su u metrima prema pravoj poziciji; ± je 1σ iz kovarijance P. Sat: predviđeno ${fmt(k.predicted.clock_m, 1)} m → ažurirano ${fmt(k.updated.clock_m, 1)} m (istina ${fmt(k.true_clock_m, 1)} m). NIS = ${fmt(k.nis)} uz ${k.nis_dof} mjerenja (očekivano ≈ ${k.nis_dof}).`
      : `Errors in metres relative to the true position; ± is 1σ from covariance P. Clock: predicted ${fmt(k.predicted.clock_m, 1)} m → updated ${fmt(k.updated.clock_m, 1)} m (truth ${fmt(k.true_clock_m, 1)} m). NIS = ${fmt(k.nis)} with ${k.nis_dof} measurements (expected ≈ ${k.nis_dof}).`));
    const used = d.measurements.filter((m) => m.contribution_enu);
    const maxC = Math.max(0.01, ...used.flatMap((m) => (m.contribution_enu ?? []).map((v) => Math.abs(v ?? 0))));
    content.appendChild(h("div", "inside-card-title", hr ? "Doprinos svakog satelita korekciji (K·inovacija, ENU)" : "Each satellite's contribution to the correction (K·innovation, ENU)"));
    content.appendChild(table(["sat", hr ? "inovacija" : "innovation", hr ? "pojačanje E/N/U [m/m]" : "gain E/N/U [m/m]", "ΔE", "ΔN", "ΔU", ""],
      used.map((m) => [m.id, fmtSigned(m.innovation), (m.gain_enu ?? []).map((v) => fmt(v, 2)).join(" / "),
        ...(m.contribution_enu ?? []).map((v) => fmtSigned(v)),
        bar1(m.contribution_enu?.[1] ?? 0, maxC)]), "mono"));
  }

  // ---- 4. RAIM ----------------------------------------------------------
  function renderRaim(d: Inspect): void {
    content.appendChild(para("intro_raim"));
    const r = d.raim;
    const hr = getLang() === "hr";
    const ig = r.integrity as { status?: string; hpl?: number; vpl?: number; hal?: number; excluded?: string[] };
    const tiles = h("div", "inside-tiles");
    const tile = (k: string, v: string) => { const t = h("div", "inside-tile"); t.append(h("span", "inside-tile-k", k), h("div", "inside-tile-v", v)); tiles.appendChild(t); };
    tile("status", ig.status ?? "—");
    tile("T", fmt(r.test)); tile("T_d", fmt(r.threshold)); tile("dof", String(r.dof ?? "—"));
    tile("√λ", fmt(r.pbias)); tile("HPL", ig.hpl != null ? ig.hpl.toFixed(0) + " m" : "—");
    tile("VPL", ig.vpl != null ? ig.vpl.toFixed(0) + " m" : "—");
    content.appendChild(tiles);
    if (r.pdf_x && r.pdf_y && r.threshold != null && r.test != null) {
      const cv = document.createElement("canvas");
      cv.className = "inside-canvas";
      content.appendChild(cv);
      const span = (r.pdf_x[r.pdf_x.length - 1] || 1) * 0.004;
      requestAnimationFrame(() => drawLine(cv, [{ label: `χ²(${r.dof})`, color: "#24d3ed", data: r.pdf_y! }], {
        x: r.pdf_x, yLabel: "p(T)", xLabel: "T",
        bands: [
          { from: r.threshold! - span, to: r.threshold! + span, color: "rgba(247,107,107,0.9)" },
          { from: r.test! - span, to: r.test! + span, color: "rgba(250,191,41,0.95)" },
          { from: r.threshold!, to: r.pdf_x![r.pdf_x!.length - 1], color: "rgba(247,107,107,0.10)" },
        ],
      }));
      content.appendChild(h("p", "inside-note", hr
        ? `Krivulja: razdioba T kad NEMA kvara. Žuta crta = izmjereni T, crvena = prag T_d (P_FA = ${(r.pfa ?? 0).toExponential(0)}); crvena zona = alarm. Ako T padne u nju, RAIM isključi satelit s najvećim normaliziranim rezidualom.`
        : `Curve: distribution of T with NO fault. Yellow line = measured T, red = threshold T_d (P_FA = ${(r.pfa ?? 0).toExponential(0)}); red zone = alarm. If T lands there, RAIM excludes the satellite with the largest normalized residual.`));
    }
    if (r.sats) {
      const maxW = Math.max(3, ...r.sats.map((s) => Math.abs(s.normalized ?? 0)));
      const maxS = Math.max(0.1, ...r.sats.map((s) => s.hslope ?? 0));
      content.appendChild(table(["sat", hr ? "rezidual [m]" : "residual [m]", hr ? "normaliziran" : "normalized", "", "H slope", "", "V slope"],
        r.sats.map((s) => [s.id, fmtSigned(s.residual), fmt(s.normalized), bar1(s.normalized, maxW, "var(--amber)"),
          fmt(s.hslope), bar1(s.hslope, maxS, "var(--green)"), fmt(s.vslope)]), "mono"));
      content.appendChild(h("p", "inside-note", hr
        ? "Satelit s najvećim nagibom je 'najopasniji': njegov kvar najviše pomiče poziciju, a najmanje se vidi u testu. HPL = najveći H nagib × √λ."
        : "The satellite with the largest slope is the 'most dangerous': its fault moves the position most while showing least in the test. HPL = largest H slope × √λ."));
    } else {
      content.appendChild(h("p", "inside-note", hr ? "Premalo satelita za RAIM (nema redundancije)." : "Too few satellites for RAIM (no redundancy)."));
    }
  }

  function render(): void {
    renderChrome();
    clear(content);
    const d = data;
    if (!d) { status.textContent = "…"; return; }
    if (!d.available) {
      status.textContent = "";
      content.appendChild(h("p", "inside-intro", tx(d.reason === "no_receiver" ? "no_receiver" : "no_solution")));
      return;
    }
    status.textContent = tx("status").replace("{t}", fmt(d.sim_time, 0)).replace("{e}", fmt(d.error_m, 1));
    if (tab === "meas") renderMeas(d);
    else if (tab === "geom") renderGeom(d);
    else if (tab === "kal") renderKal(d);
    else renderRaim(d);
  }

  function hide(): void {
    overlay.style.display = "none";
    if (timer != null) { window.clearInterval(timer); timer = null; }
  }

  onLangChange(() => { if (overlay.style.display !== "none") render(); });

  return {
    open(): void {
      overlay.style.display = "flex";
      setAuto();
      void load();
    },
  };
}
