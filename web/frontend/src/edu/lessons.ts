// GPS učilište — vođene interaktivne lekcije. Korak-po-korak vode korisnika i
// SAME pogone kontrolni panel (postave prijemnik, pokrenu napad, promijene doba
// dana...) te istaknu dio sučelja. Sadržaj dolazi iz content/lessons.{hr,en}.json.
import { api, type Lesson, type LessonAction } from "../lib/api";
import { t, getLang, onLangChange } from "../lib/i18n";
import { h, clear } from "../lib/dom";

// Što lekcija može napraviti s aplikacijom (implementira main.ts).
export interface LessonDriver {
  place(lat: number, lon: number): void;
  attack(v: string): void;
  timeOfDay(hour: number): void;
  raim(on: boolean): void;
  kinematic(on: boolean): void;
  speed(v: number): void;
  play(): void;
  pause(): void;
  reset(): void;
  experiment(tab: string): void;
  flyTo(lat: number, lon: number): void;
}

// Naziv istaknutog cilja -> selektor stabilnog kontejnera u sučelju.
const HILITE: Record<string, string> = {
  controls: ".panel-left",
  telemetry: ".panel-right",
  globe: "#cesium",
  dock: ".dock",
};

export function mountLessons(driver: LessonDriver): { open: () => void } {
  const overlay = h("div", "lesson-overlay");
  overlay.style.display = "none";
  const card = h("div", "lesson-card");
  overlay.appendChild(card);
  document.body.appendChild(overlay);

  // Istaknuti okvir (glow) koji se pomiče preko sučelja.
  const ring = h("div", "lesson-ring");
  ring.style.display = "none";
  document.body.appendChild(ring);

  let lessons: Lesson[] = [];
  let loaded = false;
  let current: Lesson | null = null;
  let step = 0;

  async function ensureLoaded(): Promise<void> {
    try {
      lessons = (await api.lessons(getLang())).lessons ?? [];
    } catch {
      lessons = [];
    }
    loaded = true;
  }
  onLangChange(() => { loaded = false; });   // ponovno učitaj na promjenu jezika

  function dispatch(a?: LessonAction): void {
    if (!a) return;
    switch (a.do) {
      case "place": if (a.lat != null && a.lon != null) { driver.place(a.lat, a.lon); driver.flyTo(a.lat, a.lon); } break;
      case "attack": driver.attack(String(a.value ?? "none")); break;
      case "time_of_day": driver.timeOfDay(Number(a.hour ?? 14)); break;
      case "raim": driver.raim(a.on !== false); break;
      case "kinematic": driver.kinematic(a.on === true); break;
      case "speed": driver.speed(Number(a.value ?? 100)); break;
      case "play": driver.play(); break;
      case "pause": driver.pause(); break;
      case "reset": driver.reset(); break;
      case "experiment": driver.experiment(String(a.tab ?? "rtk")); break;
    }
  }

  function highlight(name?: string): void {
    const sel = name ? HILITE[name] : undefined;
    const el = sel ? document.querySelector<HTMLElement>(sel) : null;
    if (!el) { ring.style.display = "none"; return; }
    const r = el.getBoundingClientRect();
    ring.style.display = "block";
    ring.style.top = `${r.top - 6}px`;
    ring.style.left = `${r.left - 6}px`;
    ring.style.width = `${r.width + 12}px`;
    ring.style.height = `${r.height + 12}px`;
  }

  function renderList(): void {
    current = null;
    highlight();
    clear(card);
    card.appendChild(h("div", "lesson-head", t("lessons")));
    if (!lessons.length) { card.appendChild(h("div", "lesson-text", "—")); addClose(); return; }
    const list = h("div", "lesson-list");
    for (const les of lessons) {
      const item = h("button", "lesson-item");
      item.appendChild(h("div", "lesson-item-title", les.title));
      item.appendChild(h("div", "lesson-item-sum", les.summary));
      item.addEventListener("click", () => { current = les; step = 0; renderStep(); });
      list.appendChild(item);
    }
    card.appendChild(list);
    addClose();
  }

  function renderStep(): void {
    if (!current) return renderList();
    const steps = current.steps;
    if (!steps.length) { renderList(); return; }
    step = Math.max(0, Math.min(step, steps.length - 1));
    const s = steps[step];
    dispatch(s.action);
    highlight(s.highlight);

    clear(card);
    const head = h("div", "lesson-head");
    head.appendChild(h("span", "lesson-title-txt", current.title));
    head.appendChild(h("span", "lesson-count", `${step + 1} / ${steps.length}`));
    card.appendChild(head);

    const bar = h("div", "lesson-progress");
    const fill = h("div", "lesson-progress-fill");
    fill.style.width = `${((step + 1) / steps.length) * 100}%`;
    bar.appendChild(fill);
    card.appendChild(bar);

    card.appendChild(h("div", "lesson-text", s.text));

    const nav = h("div", "lesson-nav");
    const back = h("button", "btn lesson-btn", "‹");
    back.addEventListener("click", () => { step -= 1; if (step < 0) renderList(); else renderStep(); });
    const menu = h("button", "btn lesson-btn", t("lessons"));
    menu.addEventListener("click", renderList);
    const next = h("button", "btn primary lesson-btn",
      step === steps.length - 1 ? t("lesson_done") : t("lesson_next"));
    next.addEventListener("click", () => {
      if (step === steps.length - 1) renderList();
      else { step += 1; renderStep(); }
    });
    nav.append(back, menu, next);
    card.appendChild(nav);
  }

  function addClose(): void {
    const nav = h("div", "lesson-nav");
    const close = h("button", "btn primary lesson-btn", t("lesson_close"));
    close.addEventListener("click", hide);
    nav.appendChild(close);
    card.appendChild(nav);
  }

  function hide(): void { overlay.style.display = "none"; highlight(); }

  // istaknuti okvir prati promjenu veličine prozora dok je lekcija otvorena
  window.addEventListener("resize", () => {
    if (overlay.style.display !== "none" && current) highlight(current.steps[step]?.highlight);
  });

  async function open(): Promise<void> {
    if (!loaded) await ensureLoaded();
    overlay.style.display = "block";
    renderList();
  }

  return { open: () => void open() };
}
