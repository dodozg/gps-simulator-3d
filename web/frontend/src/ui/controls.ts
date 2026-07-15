// Lijevi kontrolni panel: play/pause, brzina, doba dana, toggles.
import { h, clear } from "../lib/dom";
import { t, onLangChange } from "../lib/i18n";
import type { Globe } from "../globe/globe";
import type { StateFrame } from "../lib/types";

type Send = (msg: Record<string, unknown>) => void;

export function mountControls(container: HTMLElement, send: Send, globe: Globe,
                              onExperiments?: () => void, onLessons?: () => void) {
  const state = { playing: false, timeScale: 100, tow: 50400, kinematic: false, raim: true, attack: "none" };
  const show = { orbits: true, rays: true, labels: false };
  const ATTACKS: Array<[string, () => string]> = [
    ["none", () => t("atk_none")], ["coordinated", () => t("atk_coordinated")],
    ["naive", () => t("atk_naive")], ["meaconing", () => t("atk_meaconing")],
    ["jamming", () => t("atk_jamming")],
  ];

  function row(label: string): HTMLElement {
    const r = h("div", "ctl-row");
    r.appendChild(h("label", "ctl-label", label));
    return r;
  }

  function toggle(label: string, on: boolean, cb: (v: boolean) => void): HTMLElement {
    const r = row(label);
    const btn = h("button", "toggle" + (on ? " on" : ""));
    btn.setAttribute("role", "switch");
    btn.setAttribute("aria-checked", String(on));
    btn.addEventListener("click", () => {
      const v = !btn.classList.contains("on");
      btn.classList.toggle("on", v);
      btn.setAttribute("aria-checked", String(v));
      cb(v);
    });
    r.appendChild(btn);
    return r;
  }

  function selectRow(label: string, value: string, opts: Array<[string, string]>,
                     cb: (v: string) => void): HTMLElement {
    const r = row(label);
    const sel = h("select", "ctl-select") as HTMLSelectElement;
    for (const [val, lab] of opts) {
      const o = h("option", undefined, lab) as HTMLOptionElement;
      o.value = val; sel.appendChild(o);
    }
    sel.value = value;
    sel.addEventListener("change", () => cb(sel.value));
    r.appendChild(sel);
    return r;
  }

  function render(): void {
    clear(container);
    container.appendChild(h("div", "panel-title", t("controls")));

    // play / pause
    const playBtn = h("button", "btn primary", state.playing ? t("pause") : t("play"));
    playBtn.addEventListener("click", () => {
      state.playing = !state.playing;
      send({ type: state.playing ? "play" : "pause" });
      playBtn.textContent = state.playing ? t("pause") : t("play");
    });
    const resetBtn = h("button", "btn", t("reset"));
    resetBtn.addEventListener("click", () => {
      state.playing = false;
      send({ type: "reset" });
      playBtn.textContent = t("play");
    });
    const bar = h("div", "btn-bar");
    bar.append(playBtn, resetBtn);
    container.appendChild(bar);

    // brzina
    const spd = row(`${t("speed")} ×${state.timeScale}`);
    const spdIn = h("input", "slider") as HTMLInputElement;
    spdIn.type = "range"; spdIn.min = "1"; spdIn.max = "1000"; spdIn.step = "1";
    spdIn.value = String(state.timeScale);
    spdIn.addEventListener("input", () => {
      state.timeScale = Number(spdIn.value);
      spd.querySelector(".ctl-label")!.textContent = `${t("speed")} ×${state.timeScale}`;
      send({ type: "time_scale", value: state.timeScale });
    });
    spd.appendChild(spdIn);
    container.appendChild(spd);

    // doba dana (ionosfera)
    const hh = Math.floor(state.tow / 3600);
    const tod = row(`${t("time_of_day")}: ${String(hh).padStart(2, "0")}:00`);
    const todIn = h("input", "slider") as HTMLInputElement;
    todIn.type = "range"; todIn.min = "0"; todIn.max = "23"; todIn.step = "1";
    todIn.value = String(hh);
    todIn.addEventListener("input", () => {
      state.tow = Number(todIn.value) * 3600;
      tod.querySelector(".ctl-label")!.textContent =
        `${t("time_of_day")}: ${String(todIn.value).padStart(2, "0")}:00`;
      send({ type: "iono_tow0", value: state.tow });
    });
    tod.appendChild(todIn);
    container.appendChild(tod);

    // toggles koji šalju backendu
    container.appendChild(toggle(t("kinematic"), state.kinematic, (v) => {
      state.kinematic = v; send({ type: "kinematic", on: v });
    }));
    container.appendChild(toggle(t("raim"), state.raim, (v) => {
      state.raim = v; send({ type: "raim", on: v });
    }));

    // živi napad (spoofing/jamming) — prozor se na backendu sidri na "sada"
    container.appendChild(selectRow(t("f_attack"), state.attack,
      ATTACKS.map(([v, lab]) => [v, lab()] as [string, string]), (v) => {
        state.attack = v;
        send({ type: "attack", spec: v === "none" ? null : v });
      }));

    // toggles prikaza (samo klijent)
    container.appendChild(h("div", "panel-sub", t("systems")));
    container.appendChild(toggle(t("show_orbits"), show.orbits, (v) => { show.orbits = v; globe.setShow("orbits", v); }));
    container.appendChild(toggle(t("show_rays"), show.rays, (v) => { show.rays = v; globe.setShow("rays", v); }));
    container.appendChild(toggle(t("show_labels"), show.labels, (v) => { show.labels = v; globe.setShow("labels", v); }));

    // eksperimenti (Faza 2)
    if (onExperiments || onLessons) {
      container.appendChild(h("div", "panel-sub", t("academy")));
      if (onLessons) {
        const les = h("button", "btn primary exp-open-btn", t("open_lessons"));
        les.addEventListener("click", onLessons);
        container.appendChild(les);
      }
      if (onExperiments) {
        const exp = h("button", "btn exp-open-btn", t("open_experiments"));
        exp.addEventListener("click", onExperiments);
        container.appendChild(exp);
      }
    }

    container.appendChild(h("div", "hint", t("place_hint")));
  }

  render();
  onLangChange(render);

  // Backend sesija je singleton koji preživi osvježavanje stranice, a kontrole se
  // resetiraju na zadane vrijednosti -> moguća desinkronizacija (npr. kinematički
  // ostane uključen na backendu, a toggle prikazuje isključeno). Zato pri svakom
  // (ponovnom) spajanju uskladimo UI s PRAVIM stanjem iz prvog frame-a.
  let needSync = true;
  return {
    syncFromFrame(f: StateFrame): void {
      if (needSync) {
        state.playing = f.playing;
        state.timeScale = f.time_scale;
        state.tow = f.iono_tow0;
        state.kinematic = f.kinematic;
        state.raim = f.raim_enabled;
        state.attack = f.attack ? f.attack.type : "none";
        needSync = false;
        render();                                   // jednokratno; ne bori se s unosom
        return;
      }
      state.playing = f.playing;
      const btn = container.querySelector(".btn.primary");
      if (btn) btn.textContent = state.playing ? t("pause") : t("play");
    },
    resync(): void { needSync = true; },            // pozovi na ponovno spajanje
    // Programsko podešavanje (vođene lekcije): ažurira stanje, pošalje backendu,
    // pa ponovno iscrta panel da UI odražava promjenu.
    set(patch: Partial<{ playing: boolean; timeScale: number; tow: number;
                         kinematic: boolean; raim: boolean; attack: string }>): void {
      if (patch.playing !== undefined) { state.playing = patch.playing; send({ type: patch.playing ? "play" : "pause" }); }
      if (patch.timeScale !== undefined) { state.timeScale = patch.timeScale; send({ type: "time_scale", value: patch.timeScale }); }
      if (patch.tow !== undefined) { state.tow = patch.tow; send({ type: "iono_tow0", value: patch.tow }); }
      if (patch.kinematic !== undefined) { state.kinematic = patch.kinematic; send({ type: "kinematic", on: patch.kinematic }); }
      if (patch.raim !== undefined) { state.raim = patch.raim; send({ type: "raim", on: patch.raim }); }
      if (patch.attack !== undefined) { state.attack = patch.attack; send({ type: "attack", spec: patch.attack === "none" ? null : patch.attack }); }
      render();
    },
  };
}
