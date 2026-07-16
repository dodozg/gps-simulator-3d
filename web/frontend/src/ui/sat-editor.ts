// Editor pojedinog satelita: ubrizgaj kvar sata (RAIM demo) i mijenjaj orbitu.
// Plutajuća kartica (ne blokira globus) — otvara se klikom na redak u tablici
// satelita. Uređivačke vrijednosti se postave pri otvaranju; svaki frame se
// osvježava samo status (elevacija / prati / RAIM), da se ne bori s unosom.
import { h } from "../lib/dom";
import { t, onLangChange } from "../lib/i18n";
import type { StateFrame, SatFrame } from "../lib/types";

type Send = (msg: Record<string, unknown>) => void;

export function mountSatEditor(parent: HTMLElement, send: Send) {
  let curId: string | null = null;
  let last: StateFrame | null = null;

  const card = h("div", "sat-editor");
  card.style.display = "none";

  const head = h("div", "sat-editor-head");
  const titleEl = h("div", "sat-editor-title");
  const closeBtn = h("button", "modal-close", "×");
  closeBtn.addEventListener("click", () => hide());
  head.append(titleEl, closeBtn);

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
  function numField(labelKey: string, param: "alt_km" | "inc_deg", step: number): { wrap: HTMLElement; input: HTMLInputElement } {
    const wrap = h("div", "sat-editor-field");
    const lab = h("label", "ctl-label");
    lab.dataset.k = labelKey;
    const input = h("input", "ctl-select") as HTMLInputElement;
    input.type = "number"; input.step = String(step);
    input.addEventListener("change", () => {
      if (curId && input.value !== "") send({ type: "set_sat_param", id: curId, param, value: Number(input.value) });
    });
    wrap.append(lab, input);
    return { wrap, input };
  }
  const altF = numField("sat_altitude", "alt_km", 100);
  const incF = numField("sat_inclination", "inc_deg", 1);

  const resetBtn = h("button", "btn", "");
  resetBtn.addEventListener("click", () => {
    faultSlider.value = "0"; faultVal.textContent = "0 m";
    if (curId) send({ type: "set_sat_param", id: curId, param: "clock_offset_m", value: 0 });
  });

  card.append(head, statusEl, faultWrap, altF.wrap, incF.wrap, resetBtn);
  parent.appendChild(card);

  function find(id: string): SatFrame | undefined {
    return last?.satellites.find((s) => s.id === id);
  }

  function applyLabels(): void {
    faultLabel.textContent = t("sat_clock_fault");
    faultNote.textContent = t("sat_fault_note");
    altF.wrap.querySelector("label")!.textContent = t("sat_altitude");
    incF.wrap.querySelector("label")!.textContent = t("sat_inclination");
    resetBtn.textContent = t("sat_reset_health");
  }

  function statusText(s: SatFrame): string {
    const st = s.rejected ? t("sat_status_rejected")
      : s.tracked ? t("sat_status_tracked")
      : (s.el != null && s.el >= 0) ? t("sat_status_visible") : t("sat_status_hidden");
    const el = s.el != null ? `  ·  ${s.el.toFixed(0)}°` : "";
    return `${s.system}  ·  ${st}${el}`;
  }

  function refreshStatus(): void {
    if (!curId) return;
    const s = find(curId);
    if (s) statusEl.textContent = statusText(s);
  }

  function hide(): void { curId = null; card.style.display = "none"; }

  applyLabels();
  onLangChange(() => { applyLabels(); refreshStatus(); });

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
      refreshStatus();
      card.style.display = "block";
    },
    update(f: StateFrame): void {
      last = f;
      if (curId) refreshStatus();
    },
    close: hide,
  };
}
