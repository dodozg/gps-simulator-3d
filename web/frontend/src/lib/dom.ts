// Sitni DOM helperi (bez frameworka).
export function h(tag: string, cls?: string, text?: string): HTMLElement {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

export function clear(e: HTMLElement): void {
  while (e.firstChild) e.removeChild(e.firstChild);
}

// Vrijednost s klikabilnim pojmom (pojmovnik) — <span data-term="GDOP">.
export function term(key: string, label?: string): HTMLElement {
  const s = h("span", "term", label ?? key);
  s.dataset.term = key;
  return s;
}

// Kao term(), ali okida OBJEDINJENI info-popover (definicija + živo tumačenje).
// Koristi se u telemetriji; data-info nosi id koncepta (vidi edu/info.ts).
export function infoTerm(concept: string, label: string): HTMLElement {
  const s = h("span", "term", label);
  s.dataset.info = concept;
  return s;
}
