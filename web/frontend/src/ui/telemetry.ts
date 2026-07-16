// Desni panel: live telemetrija + tablica satelita.
// Svaka stavka ima CYAN klikabilnu oznaku (pojam) koja otvara objedinjeni
// info-popover (definicija + živo tumačenje) — vidi edu/info.ts.
//
// PERFORMANSE: skelet panela se gradi JEDNOM; update() samo mijenja tekst i
// vidljivost redaka. Prije se cijeli DOM rušio i ponovno gradio na svakom
// frameu (~10 Hz) — glavni izvor lagganja desnog panela.
import { h, term } from "../lib/dom";
import { t, onLangChange } from "../lib/i18n";
import { getMode, onModeChange } from "../lib/prefs";
import type { StateFrame, SatFrame } from "../lib/types";

function vis(node: HTMLElement, on: boolean): void {
  node.style.display = on ? "" : "none";
}

// Redak telemetrije s cyan pojmom (data-info okida popover) i vrijednošću.
interface Row { row: HTMLElement; label: HTMLElement; value: HTMLElement; }
function mkRow(concept: string, cls = ""): Row {
  const row = h("div", "tel-row " + cls);
  const l = h("div", "tel-label");
  const label = h("span", "term");           // cyan, klikabilno
  label.dataset.info = concept;
  l.appendChild(label);
  const value = h("div", "tel-value");
  row.append(l, value);
  return { row, label, value };
}

function fmtAlt(a: number | null | undefined): string {
  return a == null ? "—" : `${a.toFixed(0)} m`;
}

export function mountTelemetry(container: HTMLElement,
                               send: (msg: Record<string, unknown>) => void,
                               onSatClick?: (id: string) => void) {
  let last: StateFrame | null = null;

  // --- skelet (gradi se jednom) ---
  const title = h("div", "panel-title");
  const noFix = h("div", "hint");
  const waiting = h("div", "hint");

  const attackBanner = h("div", "attack-banner");
  const attackDot = h("span", "attack-dot");
  const attackText = h("span");
  attackBanner.append(attackDot, attackText);

  const raimBanner = h("div", "raim-banner");
  const raimTerm = term("RAIM");
  const raimMsg = h("span");
  raimBanner.append(raimTerm, raimMsg);

  const truthR = mkRow("truth");
  const estR = mkRow("estimate");
  const errR = mkRow("error", "accent");
  const altTrueR = mkRow("altitude");
  const altEstR = mkRow("altitude");
  const velTrueR = mkRow("velocity");
  const velEstR = mkRow("velocity");
  const gdopR = mkRow("gdop");
  const satsR = mkRow("sats");
  const nisR = mkRow("nis");
  const clkR = mkRow("clock");
  // ISB (inter-system bias) — po jedan redak za Galileo/GLONASS/BeiDou (multi-GNSS).
  const isbR: Record<string, Row> = { GAL: mkRow("isb"), GLO: mkRow("isb"), BDS: mkRow("isb") };

  // Tablica satelita — skelet se gradi jednom; redci se ažuriraju/premještaju
  // in-place (keyed po sat.id), bez rušenja DOM-a svaki frame.
  const tableWrap = h("div", "sat-table-wrap");
  const satTitle = h("div", "panel-sub");
  const satTbl = h("table", "sat-table");
  const satHead = h("tr");
  const satBody = document.createElement("tbody");
  satTbl.append(satHead, satBody);
  tableWrap.append(satTitle, satTbl);
  interface SatRow { tr: HTMLElement; tog: HTMLElement; enabled: boolean; id: HTMLElement; sys: HTMLElement; el: HTMLElement; az: HTMLElement; status: HTMLElement; resid: HTMLElement; }
  const satRows = new Map<string, SatRow>();

  container.append(title, attackBanner, raimBanner, noFix,
    truthR.row, estR.row, errR.row,
    altTrueR.row, altEstR.row, velTrueR.row, velEstR.row, waiting,
    gdopR.row, satsR.row, nisR.row, clkR.row,
    isbR.GAL.row, isbR.GLO.row, isbR.BDS.row, tableWrap);

  // Statične (jezično ovisne) oznake — postave se jednom i na promjenu jezika.
  function applyLabels(): void {
    title.textContent = t("telemetry");
    noFix.textContent = t("no_fix");
    waiting.textContent = t("waiting");
    raimTerm.textContent = t("raim_alarm");
    estR.label.textContent = t("estimate");
    errR.label.textContent = t("error");
    gdopR.label.textContent = "GDOP";
    satsR.label.textContent = t("sats");
    nisR.label.textContent = "NIS/dof";
    altTrueR.label.textContent = t("altitude_true");
    altEstR.label.textContent = t("altitude_est");
    velTrueR.label.textContent = t("velocity_true");
    velEstR.label.textContent = t("velocity_est");
    clkR.label.textContent = t("clock");
    isbR.GAL.label.textContent = "ISB " + t("sys_GAL");
    isbR.GLO.label.textContent = "ISB " + t("sys_GLO");
    isbR.BDS.label.textContent = "ISB " + t("sys_BDS");
    satTitle.textContent = t("satellite_table");
    satHead.replaceChildren(
      ...["", t("col_sat"), t("col_sys"), t("col_el"), t("col_az"), t("col_used"), t("col_resid")]
        .map((c) => h("th", undefined, c)));
    // truth oznaka ovisi o frameu (Istina/Let) — postavlja se u updateView().
  }

  // Ažuriranje tablice satelita in-place: postojeći redci se mijenjaju i
  // premještaju u ispravan poredak (appendChild MIČE čvor), nema recreate-a.
  function updateSatTable(sats: SatFrame[]): void {
    const shown = sats
      .filter((s) => s.el != null && s.el >= 0)
      .sort((a, b) => (b.el ?? 0) - (a.el ?? 0));
    const seen = new Set<string>();
    for (const s of shown) {
      seen.add(s.id);
      let r = satRows.get(s.id);
      if (!r) {
        const tr = h("tr");
        const tog = h("td", "sat-tog");
        const id = h("td", "mono");
        const sys = h("td");
        const el = h("td", "mono");
        const az = h("td", "mono");
        const status = h("td");
        const resid = h("td", "mono");
        tr.append(tog, id, sys, el, az, status, resid);
        const row: SatRow = { tr, tog, enabled: true, id, sys, el, az, status, resid };
        const sid = s.id;   // stabilan id za klik (s se mijenja svaki frame)
        tog.addEventListener("click", (ev) => {
          ev.stopPropagation();
          send({ type: "set_sat", id: sid, on: !row.enabled });
        });
        if (onSatClick) {
          tr.classList.add("sat-clickable");
          tr.addEventListener("click", () => onSatClick(sid));   // toggle radi stopPropagation
        }
        satRows.set(s.id, row);
        r = row;
      }
      r.enabled = s.enabled !== false;
      r.tog.textContent = r.enabled ? "●" : "○";
      r.tog.title = r.enabled ? t("sat_off") : t("sat_on");
      r.tr.className = (s.rejected ? "rejected" : s.tracked ? "tracked" : "")
        + (r.enabled ? "" : " sat-disabled");
      r.id.textContent = s.id;
      r.sys.textContent = s.system;
      r.el.textContent = s.el != null ? s.el.toFixed(0) + "°" : "—";
      r.az.textContent = s.az != null ? s.az.toFixed(0) + "°" : "—";
      r.status.textContent = s.rejected ? t("used_rejected") : s.tracked ? t("used_yes") : t("used_visible");
      r.resid.textContent = s.residual_m != null ? s.residual_m.toFixed(0) + " m" : "—";
      satBody.appendChild(r.tr);   // premjesti u sortirani položaj
    }
    for (const [id, r] of satRows) {
      if (!seen.has(id)) { r.tr.remove(); satRows.delete(id); }
    }
  }

  function updateView(): void {
    const f = last;
    const placed = !!(f && f.receiver.placed);
    vis(noFix, !placed);
    if (!f || !placed) {
      [attackBanner, raimBanner, truthR.row, estR.row, errR.row,
       altTrueR.row, altEstR.row, velTrueR.row, velEstR.row, waiting,
       gdopR.row, satsR.row, nisR.row, clkR.row,
       isbR.GAL.row, isbR.GLO.row, isbR.BDS.row, tableWrap]
        .forEach((n) => vis(n, false));
      return;
    }
    const rx = f.receiver;
    const expert = getMode() === "expert";

    // banner napada
    if (f.attack) {
      vis(attackBanner, true);
      const armed = !f.attack_active;
      attackBanner.classList.toggle("armed", armed);
      attackText.textContent =
        (f.attack_active ? t("attack_active_banner") : t("attack_armed")) + " — " + t("atk_" + f.attack.type);
    } else vis(attackBanner, false);

    // RAIM alarm
    if (f.raim_alarm) {
      vis(raimBanner, true);
      raimMsg.textContent = "  " + f.raim_alarm;
    } else vis(raimBanner, false);

    // koordinate + visina + brzina (istina) — poznato čim je rover postavljen
    if (rx.truth) {
      vis(truthR.row, true);
      truthR.label.textContent = t(f.kinematic ? "flying" : "truth");
      truthR.value.textContent = `${rx.truth.dms.lat}  ${rx.truth.dms.lon}`;
      vis(altTrueR.row, true);
      altTrueR.value.textContent = fmtAlt(rx.truth.lla.alt);
      vis(velTrueR.row, true);
      velTrueR.value.textContent = (rx.velocity_true_ms ?? 0).toFixed(1) + " m/s";
    } else { vis(truthR.row, false); vis(altTrueR.row, false); vis(velTrueR.row, false); }

    // procjena: koordinate + greška + visina + brzina, ili "čekam rješenje"
    if (rx.ekf_initialized && rx.estimate) {
      vis(estR.row, true);
      estR.value.textContent = `${rx.estimate.dms.lat}  ${rx.estimate.dms.lon}`;
      const hasErr = rx.error_m != null;
      vis(errR.row, hasErr);
      if (hasErr) errR.value.textContent = rx.error_m!.toFixed(1) + " m";
      vis(altEstR.row, true);
      altEstR.value.textContent = fmtAlt(rx.estimate.lla.alt);
      vis(velEstR.row, true);
      velEstR.value.textContent = (rx.velocity_ms ?? 0).toFixed(1) + " m/s";
      vis(waiting, false);
    } else {
      vis(estR.row, false); vis(errR.row, false);
      vis(altEstR.row, false); vis(velEstR.row, false); vis(waiting, true);
    }

    // integritet i geometrija
    vis(gdopR.row, true);
    gdopR.value.textContent = rx.gdop != null ? rx.gdop.toFixed(2) : "—";
    vis(satsR.row, true);
    satsR.value.textContent = `${f.sats_tracked}/${f.sats_total} ${t("tracked")}`;

    // stručni redci
    vis(nisR.row, expert);
    if (expert) nisR.value.textContent = rx.nis_ratio != null ? rx.nis_ratio.toFixed(2) : "—";
    vis(clkR.row, expert);
    if (expert) clkR.value.textContent = rx.clock_bias_us.toFixed(1) + " µs";

    // ISB (inter-system bias) — procjena → istina, po aktivnom ne-GPS sustavu
    const active = new Set<string>();
    if (expert) for (const e of rx.isb ?? []) {
      const row = isbR[e.system];
      if (!row) continue;
      active.add(e.system);
      row.value.textContent = (e.est != null ? e.est.toFixed(1) : "—") + " → " + e.true.toFixed(0) + " m";
    }
    for (const sy of ["GAL", "GLO", "BDS"]) vis(isbR[sy].row, expert && active.has(sy));

    vis(tableWrap, expert);
    if (expert) updateSatTable(f.satellites);
  }

  applyLabels();
  updateView();
  onLangChange(() => { applyLabels(); updateView(); });
  onModeChange(updateView);

  return {
    update(f: StateFrame): void {
      last = f;
      updateView();
    },
  };
}
