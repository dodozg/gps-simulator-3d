// Mali kontrolni panel pojedinog satelita: uključi/isključi, ubrizgaj kvar sata
// (RAIM demo), mijenjaj orbitu (visina/inklinacija/RAAN), fokusiraj kameru + žive
// informacije (elevacija/azimut/rezidual/status). Plutajuća kartica (ne blokira
// globus) — otvara se klikom na redak u tablici satelita ILI na oznaku satelita na
// globusu. Uređivačke vrijednosti se postave pri otvaranju; svaki frame se osvježe
// samo žive informacije, da se ne bore s unosom.
import { h } from "../lib/dom";
import { t, onLangChange } from "../lib/i18n";
import type { StateFrame, SatFrame } from "../lib/types";

type Send = (msg: Record<string, unknown>) => void;
type OnFocus = (ecef: [number, number, number]) => void;

export function mountSatEditor(parent: HTMLElement, send: Send, onFocus?: OnFocus) {
  let curId: string | null = null;
  let last: StateFrame | null = null;

  const card = h("div", "sat-editor");
  card.style.display = "none";

  const head = h("div", "sat-editor-head");
  const titleEl = h("div", "sat-editor-title");
  const closeBtn = h("button", "modal-close", "×");
  closeBtn.addEventListener("click", () => hide());
  head.append(titleEl, closeBtn);

  // --- uključi/isključi satelit ---
  const enRow = h("div", "ctl-row toggle-row");
  const enLabel = h("label", "ctl-label");
  const enBtn = h("button", "toggle");
  enBtn.setAttribute("role", "switch");
  enBtn.addEventListener("click", () => {
    const on = !enBtn.classList.contains("on");
    enBtn.classList.toggle("on", on);
    enBtn.setAttribute("aria-checked", String(on));
    if (curId) send({ type: "set_sat", id: curId, on });
  });
  enRow.append(enLabel, enBtn);

  // --- žive informacije (elevacija / azimut / rezidual) ---
  const info = h("div", "sat-editor-info");
  function infoRow(): { row: HTMLElement; label: HTMLElement; val: HTMLElement } {
    const row = h("div", "sat-editor-info-row");
    const label = h("span", "sat-editor-info-k");
    const val = h("span", "sat-editor-info-v", "—");
    row.append(label, val);
    info.appendChild(row);
    return { row, label, val };
  }
  const elRow = infoRow();
  const azRow = infoRow();
  const resRow = infoRow();

  const statusEl = h("div", "sat-editor-status");

  // --- kvar sata ---
  const faultWrap = h("div", "sat-editor-field");
  const faultLabel = h("label", "ctl-label");
  const faultRow = h("div", "sat-editor-inline");
  const faultSlider = h("input", "slider") as HTMLInputElement;
  faultSlider.type = "range"; faultSlider.min = "0"; faultSlider.max = "5000"; faultSlider.step = "50";
  const faultVal = h("span", "sat-editor-val");
  faultRow.append(faultSlider, faultVal);
  const faultNote = h("div", "sat-editor-note");
  faultWrap.append(faultLabel, faultRow, faultNote);
  faultSlider.addEventListener("input", () => {
    faultVal.textContent = faultSlider.value + " m";
    if (curId) send({ type: "set_sat_param", id: curId, param: "clock_offset_m", value: Number(faultSlider.value) });
  });

  // --- orbita ---
  const orbitTitle = h("div", "sat-editor-subhead");
  function numField(param: "alt_km" | "inc_deg" | "lan_deg", step: number): { wrap: HTMLElement; input: HTMLInputElement; lab: HTMLElement } {
    const wrap = h("div", "sat-editor-field");
    const lab = h("label", "ctl-label");
    const input = h("input", "ctl-select") as HTMLInputElement;
    input.type = "number"; input.step = String(step);
    input.addEventListener("change", () => {
      if (curId && input.value !== "") send({ type: "set_sat_param", id: curId, param, value: Number(input.value) });
    });
    wrap.append(lab, input);
    return { wrap, input, lab };
  }
  const altF = numField("alt_km", 100);
  const incF = numField("inc_deg", 1);
  const lanF = numField("lan_deg", 5);

  // --- akcije ---
  const btnRow = h("div", "sat-editor-inline");
  const focusBtn = h("button", "btn");
  focusBtn.addEventListener("click", () => {
    const s = curId ? find(curId) : undefined;
    if (s && onFocus) onFocus(s.ecef);
  });
  const resetBtn = h("button", "btn");
  resetBtn.addEventListener("click", () => {
    faultSlider.value = "0"; faultVal.textContent = "0 m";
    if (curId) send({ type: "set_sat_param", id: curId, param: "clock_offset_m", value: 0 });
  });
  btnRow.append(focusBtn, resetBtn);

  card.append(head, enRow, info, statusEl, faultWrap, orbitTitle, altF.wrap, incF.wrap, lanF.wrap, btnRow);
  parent.appendChild(card);

  function find(id: string): SatFrame | undefined {
    return last?.satellites.find((s) => s.id === id);
  }

  function applyLabels(): void {
    enLabel.textContent = t("sat_enabled");
    elRow.label.textContent = t("sat_info_el");
    azRow.label.textContent = t("sat_info_az");
    resRow.label.textContent = t("sat_info_res");
    faultLabel.textContent = t("sat_clock_fault");
    faultNote.textContent = t("sat_fault_note");
    orbitTitle.textContent = t("sat_orbit");
    altF.lab.textContent = t("sat_altitude");
    incF.lab.textContent = t("sat_inclination");
    lanF.lab.textContent = t("sat_raan");
    focusBtn.textContent = t("sat_focus");
    resetBtn.textContent = t("sat_reset_health");
  }

  function statusText(s: SatFrame): string {
    const st = s.rejected ? t("sat_status_rejected")
      : s.tracked ? t("sat_status_tracked")
      : (s.el != null && s.el >= 0) ? t("sat_status_visible") : t("sat_status_hidden");
    return `${s.system}  ·  ${st}`;
  }

  // Žive informacije + status (svaki frame). NE dira polja za unos orbite.
  function refreshLive(): void {
    if (!curId) return;
    const s = find(curId);
    if (!s) return;
    statusEl.textContent = statusText(s);
    elRow.val.textContent = s.el != null ? `${s.el.toFixed(1)}°` : "—";
    azRow.val.textContent = s.az != null ? `${s.az.toFixed(0)}°` : "—";
    resRow.val.textContent = s.residual_m != null ? `${s.residual_m.toFixed(1)} m` : "—";
    resRow.val.classList.toggle("bad", s.rejected === true);
  }

  // on/off prekidač sinkroniziramo SAMO pri otvaranju (kao i polja orbite), da
  // optimistični klik ne "vrati" prije nego backend odgovori u sljedećem frameu.
  function syncEnabled(s: SatFrame | undefined): void {
    const on = s?.enabled !== false;
    enBtn.classList.toggle("on", on);
    enBtn.setAttribute("aria-checked", String(on));
  }

  function hide(): void { curId = null; card.style.display = "none"; }

  applyLabels();
  onLangChange(() => { applyLabels(); refreshLive(); });

  return {
    open(satId: string): void {
      curId = satId;
      const s = find(satId);
      titleEl.textContent = `${t("edit_sat")} ${satId}`;
      const p = s?.params;
      const clk = p ? p.clock_offset_m : 0;
      faultSlider.value = String(Math.min(5000, Math.max(0, Math.round(clk))));
      faultVal.textContent = faultSlider.value + " m";
      altF.input.value = p ? p.alt_km.toFixed(0) : "";
      incF.input.value = p ? p.inc_deg.toFixed(1) : "";
      lanF.input.value = p ? p.lan_deg.toFixed(0) : "";
      syncEnabled(s);
      refreshLive();
      card.style.display = "block";
    },
    update(f: StateFrame): void {
      last = f;
      if (curId) refreshLive();
    },
    close: hide,
  };
}
