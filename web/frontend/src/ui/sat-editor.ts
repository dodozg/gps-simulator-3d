// Mali kontrolni panel pojedinog satelita: uključi/isključi, napadi (kvar sata,
// spoof pozicije), orbita (visina/inklinacija/RAAN/ekscentricitet), fokus kamere
// + žive informacije (elevacija/azimut/rezidual/status). Plutajuća kartica —
// otvara se klikom na redak u tablici satelita ILI na satelit na globusu.
// Uređivačke vrijednosti se postave pri otvaranju; svaki frame se osvježe samo
// žive informacije, da se ne bore s unosom.
import { h } from "../lib/dom";
import { t, onLangChange } from "../lib/i18n";
import type { StateFrame, SatFrame } from "../lib/types";

type Send = (msg: Record<string, unknown>) => void;
type OnFocus = (ecef: [number, number, number]) => void;
type OnSelect = (id: string | null) => void;
type SatParam = "clock_offset_m" | "pos_offset_m" | "alt_km" | "inc_deg" | "lan_deg" | "ecc";

export function mountSatEditor(parent: HTMLElement, send: Send, onFocus?: OnFocus, onSelect?: OnSelect) {
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

  // --- žive informacije ---
  const info = h("div", "sat-editor-info");
  function infoRow(): { label: HTMLElement; val: HTMLElement } {
    const row = h("div", "sat-editor-info-row");
    const label = h("span", "sat-editor-info-k");
    const val = h("span", "sat-editor-info-v", "—");
    row.append(label, val);
    info.appendChild(row);
    return { label, val };
  }
  const elRow = infoRow();
  const azRow = infoRow();
  const resRow = infoRow();
  const statusEl = h("div", "sat-editor-status");

  // --- slider (kvar sata / spoof pozicije) ---
  function sliderField(param: SatParam, max: number, step: number) {
    const wrap = h("div", "sat-editor-field");
    const label = h("label", "ctl-label");
    const row = h("div", "sat-editor-inline");
    const slider = h("input", "slider") as HTMLInputElement;
    slider.type = "range"; slider.min = "0"; slider.max = String(max); slider.step = String(step);
    const val = h("span", "sat-editor-val");
    row.append(slider, val);
    const note = h("div", "sat-editor-note");
    wrap.append(label, row, note);
    slider.addEventListener("input", () => {
      val.textContent = slider.value + " m";
      if (curId) send({ type: "set_sat_param", id: curId, param, value: Number(slider.value) });
    });
    return { wrap, label, slider, val, note };
  }
  const attacksTitle = h("div", "sat-editor-subhead");
  const faultF = sliderField("clock_offset_m", 5000, 50);
  const spoofF = sliderField("pos_offset_m", 5000, 50);

  // --- orbita (brojčana polja) ---
  const orbitTitle = h("div", "sat-editor-subhead");
  function numField(param: SatParam, step: number) {
    const wrap = h("div", "sat-editor-field");
    const label = h("label", "ctl-label");
    const input = h("input", "ctl-select") as HTMLInputElement;
    input.type = "number"; input.step = String(step);
    input.addEventListener("change", () => {
      if (curId && input.value !== "") send({ type: "set_sat_param", id: curId, param, value: Number(input.value) });
    });
    wrap.append(label, input);
    return { wrap, label, input };
  }
  const altF = numField("alt_km", 100);
  const incF = numField("inc_deg", 1);
  const lanF = numField("lan_deg", 5);
  const eccF = numField("ecc", 0.01);

  // --- akcije ---
  const btnRow = h("div", "sat-editor-inline");
  const focusBtn = h("button", "btn");
  focusBtn.addEventListener("click", () => {
    const s = curId ? find(curId) : undefined;
    if (s && onFocus) onFocus(s.ecef);
  });
  const resetBtn = h("button", "btn");
  resetBtn.addEventListener("click", () => {
    faultF.slider.value = "0"; faultF.val.textContent = "0 m";
    spoofF.slider.value = "0"; spoofF.val.textContent = "0 m";
    if (curId) {
      send({ type: "set_sat_param", id: curId, param: "clock_offset_m", value: 0 });
      send({ type: "set_sat_param", id: curId, param: "pos_offset_m", value: 0 });
    }
  });
  btnRow.append(focusBtn, resetBtn);

  card.append(head, enRow, info, statusEl, attacksTitle, faultF.wrap, spoofF.wrap,
    orbitTitle, altF.wrap, incF.wrap, lanF.wrap, eccF.wrap, btnRow);
  parent.appendChild(card);

  function find(id: string): SatFrame | undefined {
    return last?.satellites.find((s) => s.id === id);
  }

  function applyLabels(): void {
    enLabel.textContent = t("sat_enabled");
    elRow.label.textContent = t("sat_info_el");
    azRow.label.textContent = t("sat_info_az");
    resRow.label.textContent = t("sat_info_res");
    attacksTitle.textContent = t("sat_attacks");
    faultF.label.textContent = t("sat_clock_fault");
    faultF.note.textContent = t("sat_fault_note");
    spoofF.label.textContent = t("sat_pos_spoof");
    spoofF.note.textContent = t("sat_spoof_note");
    orbitTitle.textContent = t("sat_orbit");
    altF.label.textContent = t("sat_altitude");
    incF.label.textContent = t("sat_inclination");
    lanF.label.textContent = t("sat_raan");
    eccF.label.textContent = t("sat_ecc");
    focusBtn.textContent = t("sat_focus");
    resetBtn.textContent = t("sat_reset_health");
  }

  function statusText(s: SatFrame): string {
    const st = s.rejected ? t("sat_status_rejected")
      : s.tracked ? t("sat_status_tracked")
      : (s.el != null && s.el >= 0) ? t("sat_status_visible") : t("sat_status_hidden");
    return `${s.system}  ·  ${st}`;
  }

  // Žive informacije + status (svaki frame). NE dira polja/slidere za unos.
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

  // on/off prekidač sinkroniziramo SAMO pri otvaranju (kao i polja/slideri), da
  // optimistični klik ne "vrati" prije nego backend odgovori u sljedećem frameu.
  function syncControls(s: SatFrame | undefined): void {
    const on = s?.enabled !== false;
    enBtn.classList.toggle("on", on);
    enBtn.setAttribute("aria-checked", String(on));
    const p = s?.params;
    faultF.slider.value = String(p ? Math.min(5000, Math.max(0, Math.round(p.clock_offset_m))) : 0);
    faultF.val.textContent = faultF.slider.value + " m";
    spoofF.slider.value = String(p ? Math.min(5000, Math.max(0, Math.round(p.pos_offset_m))) : 0);
    spoofF.val.textContent = spoofF.slider.value + " m";
    altF.input.value = p ? p.alt_km.toFixed(0) : "";
    incF.input.value = p ? p.inc_deg.toFixed(1) : "";
    lanF.input.value = p ? p.lan_deg.toFixed(0) : "";
    eccF.input.value = p ? p.ecc.toFixed(3) : "";
  }

  function hide(): void {
    curId = null;
    card.style.display = "none";
    onSelect?.(null);
  }

  applyLabels();
  onLangChange(() => { applyLabels(); refreshLive(); });

  return {
    open(satId: string): void {
      curId = satId;
      const s = find(satId);
      titleEl.textContent = `${t("edit_sat")} ${satId}`;
      syncControls(s);
      refreshLive();
      card.style.display = "block";
      onSelect?.(satId);
    },
    update(f: StateFrame): void {
      last = f;
      if (curId) refreshLive();
    },
    close: hide,
  };
}
