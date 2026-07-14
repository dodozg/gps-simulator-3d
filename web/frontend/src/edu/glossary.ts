// GPS učilište — pojmovnik. Svaki element s [data-term] dobiva popover s
// objašnjenjem "na ljudskom" (kratko + detaljno + povezani pojmovi).
import { api, type GlossaryTerm } from "../lib/api";
import { t, getLang, onLangChange } from "../lib/i18n";
import { h, clear } from "../lib/dom";

let terms: Record<string, GlossaryTerm> = {};
let popover: HTMLElement | null = null;

async function load(): Promise<void> {
  try {
    terms = await api.glossary(getLang());
  } catch {
    terms = {};
  }
}

function ensurePopover(): HTMLElement {
  if (!popover) {
    popover = h("div", "glossary-popover");
    popover.style.display = "none";
    document.body.appendChild(popover);
    popover.addEventListener("mouseleave", hide);
  }
  return popover;
}

function show(target: HTMLElement, key: string): void {
  const info = terms[key] || terms[key.toUpperCase()];
  if (!info) return;
  const p = ensurePopover();
  clear(p);
  p.appendChild(h("div", "gp-term", info.term));
  p.appendChild(h("div", "gp-short", info.short));
  p.appendChild(h("div", "gp-long", info.long));
  if (info.related?.length) {
    const rel = h("div", "gp-related");
    rel.appendChild(h("span", "gp-related-label", t("related") + ": "));
    rel.appendChild(h("span", undefined, info.related.join(", ")));
    p.appendChild(rel);
  }
  const r = target.getBoundingClientRect();
  p.style.display = "block";
  const top = Math.min(r.bottom + 8, window.innerHeight - p.offsetHeight - 12);
  const left = Math.min(r.left, window.innerWidth - p.offsetWidth - 12);
  p.style.top = `${Math.max(12, top)}px`;
  p.style.left = `${Math.max(12, left)}px`;
}

function hide(): void {
  if (popover) popover.style.display = "none";
}

export async function initGlossary(): Promise<void> {
  await load();
  onLangChange(() => void load());

  document.addEventListener("mouseover", (ev) => {
    const el = (ev.target as HTMLElement)?.closest?.("[data-term]") as HTMLElement | null;
    if (el?.dataset.term) show(el, el.dataset.term);
  });
  document.addEventListener("click", (ev) => {
    const el = (ev.target as HTMLElement)?.closest?.("[data-term]") as HTMLElement | null;
    if (el?.dataset.term) show(el, el.dataset.term);
    else if (!(ev.target as HTMLElement)?.closest?.(".glossary-popover")) hide();
  });
}
