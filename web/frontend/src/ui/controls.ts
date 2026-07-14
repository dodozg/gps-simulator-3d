// Lijevi kontrolni panel: play/pause, brzina, doba dana, toggles.
import { h, clear } from "../lib/dom";
import { t, onLangChange } from "../lib/i18n";
import type { Globe } from "../globe/globe";
import type { StateFrame } from "../lib/types";

type Send = (msg: Record<string, unknown>) => void;

export function mountControls(container: HTMLElement, send: Send, globe: Globe, onExperiments?: () => void) {
  const state = { playing: false, timeScale: 100, tow: 50400, kinematic: false, raim: true };
  const show = { orbits: true, rays: true, labels: false };

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

    // toggles prikaza (samo klijent)
    container.appendChild(h("div", "panel-sub", t("systems")));
    container.appendChild(toggle(t("show_orbits"), show.orbits, (v) => { show.orbits = v; globe.setShow("orbits", v); }));
    container.appendChild(toggle(t("show_rays"), show.rays, (v) => { show.rays = v; globe.setShow("rays", v); }));
    container.appendChild(toggle(t("show_labels"), show.labels, (v) => { show.labels = v; globe.setShow("labels", v); }));

    // eksperimenti (Faza 2)
    if (onExperiments) {
      container.appendChild(h("div", "panel-sub", t("academy")));
      const exp = h("button", "btn exp-open-btn", t("open_experiments"));
      exp.addEventListener("click", onExperiments);
      container.appendChild(exp);
    }

    container.appendChild(h("div", "hint", t("place_hint")));
  }

  render();
  onLangChange(render);

  // vanjski sync (npr. nakon reseta stanja s backenda)
  return {
    syncFromFrame(f: StateFrame): void {
      state.playing = f.playing;
      const btn = container.querySelector(".btn.primary");
      if (btn) btn.textContent = state.playing ? t("pause") : t("play");
    },
  };
}
