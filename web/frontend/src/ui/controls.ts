// Lijevi kontrolni panel: play/pause, brzina, doba dana, toggles.
import { h, clear } from "../lib/dom";
import { t, onLangChange } from "../lib/i18n";
import type { Globe } from "../globe/globe";
import type { StateFrame, SystemInfo } from "../lib/types";

type Send = (msg: Record<string, unknown>) => void;

// Postavke se pamte u localStorage pa prežive i reload stranice I RESTART servera
// (backend singleton sesija se restartom vrati na defaulte -> klijent je trajni
// izvor istine i "gura" spremljeno na backend pri spajanju). Vidi pushPersisted.
const LS_KEY = "gps3d.settings";
function loadSaved(): Record<string, unknown> {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}") as Record<string, unknown>; }
  catch { return {}; }
}

export function mountControls(container: HTMLElement, send: Send, globe: Globe,
                              onExperiments?: () => void, onLessons?: () => void,
                              onGuide?: () => void) {
  const saved = loadSaved();
  const savedShow = (saved.show ?? {}) as Partial<{ orbits: boolean; rays: boolean; labels: boolean }>;
  const state = {
    playing: false,   // playing se NE pamti (ne auto-startaj nakon restarta)
    timeScale: (saved.timeScale as number) ?? 100,
    tow: (saved.tow as number) ?? 50400,
    kinematic: (saved.kinematic as boolean) ?? false,
    raim: (saved.raim as boolean) ?? true,
    attack: (saved.attack as string) ?? "none",
  };
  const show = {
    orbits: savedShow.orbits ?? true,
    rays: savedShow.rays ?? true,
    labels: savedShow.labels ?? false,
  };
  // Po sustavu spremljeno on/off (prazno = koristi backend default, GPS-only).
  const systemsOn: Record<string, boolean> = (saved.systemsOn as Record<string, boolean>) ?? {};

  function persist(): void {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({
        timeScale: state.timeScale, tow: state.tow, kinematic: state.kinematic,
        raim: state.raim, attack: state.attack, show, systemsOn,
      }));
    } catch { /* localStorage nedostupan (privatni mod) — ignoriraj */ }
  }

  let systems: Record<string, SystemInfo> | null = null;
  let systemsSig = "";
  const sigOf = (s: Record<string, SystemInfo>): string =>
    Object.entries(s).map(([k, v]) => k + (v.on ? "1" : "0")).sort().join(",");
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
    r.classList.add("toggle-row");   // flex: oznaka lijevo, prekidač desno u ISTOM retku
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
      persist();
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
      persist();
    });
    tod.appendChild(todIn);
    container.appendChild(tod);

    // prikaz globusa (samo klijent) — visoko jer se često koristi
    container.appendChild(h("div", "panel-sub", t("display")));
    container.appendChild(toggle(t("show_orbits"), show.orbits, (v) => { show.orbits = v; globe.setShow("orbits", v); persist(); }));
    container.appendChild(toggle(t("show_rays"), show.rays, (v) => { show.rays = v; globe.setShow("rays", v); persist(); }));
    container.appendChild(toggle(t("show_labels"), show.labels, (v) => { show.labels = v; globe.setShow("labels", v); persist(); }));

    // konstelacije (GPS/Galileo/GLONASS/BeiDou) — pali/gasi cijeli sustav
    if (systems) {
      container.appendChild(h("div", "panel-sub", t("systems")));
      for (const name of Object.keys(systems)) {
        const info = systems[name];
        const label = `${t("sys_" + name)}  (${info.total})`;
        // Prikaži spremljeno stanje ako postoji (prežive restart), inače backend on.
        const on = name in systemsOn ? systemsOn[name] : info.on;
        container.appendChild(toggle(label, on, (v) => {
          systemsOn[name] = v; persist();
          send({ type: "set_system", system: name, on: v });
        }));
      }
    }

    // simulacija (šalje backendu)
    container.appendChild(h("div", "panel-sub", t("simulation")));
    container.appendChild(toggle(t("kinematic"), state.kinematic, (v) => {
      state.kinematic = v; send({ type: "kinematic", on: v }); persist();
    }));
    container.appendChild(toggle(t("raim"), state.raim, (v) => {
      state.raim = v; send({ type: "raim", on: v }); persist();
    }));

    // živi napad (spoofing/jamming) — prozor se na backendu sidri na "sada"
    container.appendChild(selectRow(t("f_attack"), state.attack,
      ATTACKS.map(([v, lab]) => [v, lab()] as [string, string]), (v) => {
        state.attack = v;
        send({ type: "attack", spec: v === "none" ? null : v });
        persist();
      }));

    // eksperimenti (Faza 2)
    if (onExperiments || onLessons || onGuide) {
      container.appendChild(h("div", "panel-sub", t("academy")));
      if (onGuide) {
        const g = h("button", "btn primary exp-open-btn", t("open_guide"));
        g.addEventListener("click", onGuide);
        container.appendChild(g);
      }
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

  // Primijeni spremljene prikaz-postavke na globus odmah (globe je već stvoren).
  globe.setShow("orbits", show.orbits);
  globe.setShow("rays", show.rays);
  globe.setShow("labels", show.labels);

  // Gurni spremljene postavke na backend pri (ponovnom) spajanju. Nakon RESTARTA
  // servera sesija je na defaultima, pa je klijent taj koji vraća zadnju
  // konfiguraciju; nakon običnog reloada je ovo uglavnom no-op (backend ih već ima).
  function pushPersisted(): void {
    send({ type: "time_scale", value: state.timeScale });
    send({ type: "iono_tow0", value: state.tow });
    send({ type: "kinematic", on: state.kinematic });
    send({ type: "raim", on: state.raim });
    if (state.attack !== "none") send({ type: "attack", spec: state.attack });
    if (systems) {
      for (const name of Object.keys(systems)) {
        if (name in systemsOn) send({ type: "set_system", system: name, on: systemsOn[name] });
      }
    }
    globe.setShow("orbits", show.orbits);
    globe.setShow("rays", show.rays);
    globe.setShow("labels", show.labels);
  }

  render();
  onLangChange(render);

  // Postavke se pamte u localStorage (klijent je trajni izvor istine). Pri prvom
  // frame-u nakon (ponovnog) spajanja GURAMO spremljene postavke na backend — tako
  // prežive i reload stranice I RESTART servera (koji sesiju vrati na defaulte).
  // Iz frame-a čitamo samo ono što klijent ne zna: playing i sastav sustava.
  let needSync = true;
  return {
    syncFromFrame(f: StateFrame): void {
      if (needSync) {
        state.playing = f.playing;
        if (f.systems) { systems = f.systems; systemsSig = sigOf(f.systems); }
        pushPersisted();                            // vrati zadnju konfiguraciju na backend
        needSync = false;
        render();                                   // jednokratno; ne bori se s unosom
        return;
      }
      state.playing = f.playing;
      const btn = container.querySelector(".btn.primary");
      if (btn) btn.textContent = state.playing ? t("pause") : t("play");
      // Sustavi (konstelacije): re-render tek kad se on-stanje promijeni.
      if (f.systems) {
        const sig = sigOf(f.systems);
        if (sig !== systemsSig) { systems = f.systems; systemsSig = sig; render(); }
      }
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
      persist();
      render();
    },
  };
}
