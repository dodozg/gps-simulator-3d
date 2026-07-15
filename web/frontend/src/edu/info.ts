// GPS učilište — objedinjeni info-popover. Jedan popover pokriva DVIJE stvari:
//  • definiciju pojma (što GDOP JEST) — pojmovnik, content/glossary.*.json
//  • tumačenje TRENUTNE žive vrijednosti (što GDOP 2.3 znači sada) — good/ok/bad
// Prije su to bila dva zasebna popovera (lijevo pojam, desno "objasni ovo") koji
// su se znali preklapati; sad su spojeni u jedan.
//
// Okidači:
//  [data-term="GDOP"]   → samo definicija (hover+klik), za generičku upotrebu
//                          (dock, banneri, eksperimenti).
//  [data-info="gdop"]   → objedinjeno (klik): definicija + živo tumačenje.
import { api, type GlossaryTerm } from "../lib/api";
import { t, getLang, onLangChange } from "../lib/i18n";
import { h, clear } from "../lib/dom";
import type { StateFrame } from "../lib/types";

type Verdict = "good" | "ok" | "bad";
interface Ex { verdict: Verdict; value: string; hr: string; en: string; }

// Koncept (data-info) -> pojam u pojmovniku i/ili tumač žive vrijednosti.
const CONCEPTS: Record<string, { term?: string; explain?: string }> = {
  estimate: { term: "EKF" },
  error: { explain: "error" },
  gdop: { term: "GDOP", explain: "gdop" },
  sats: { explain: "sats" },
  nis: { term: "NIS", explain: "nis" },
  clock: { explain: "clock" },
};

// Tumači žive vrijednosti — svaki čita trenutni frame i vrati ocjenu + tekst.
const EXPLAIN: Record<string, (f: StateFrame) => Ex | null> = {
  gdop(f) {
    const g = f.receiver.gdop;
    if (g == null) return null;
    const verdict: Verdict = g < 4 ? "good" : g <= 6 ? "ok" : "bad";
    const hrTail = g < 2 ? "Odlična geometrija — sateliti su lijepo razbacani po nebu."
      : g <= 4 ? "Dobra geometrija."
      : g <= 6 ? "Osrednja — sateliti se počinju zbijati."
      : "Loša geometrija — sateliti su zbijeni (npr. kanjon zgrada), greška je napuhana.";
    const enTail = g < 2 ? "Excellent geometry — satellites nicely spread across the sky."
      : g <= 4 ? "Good geometry."
      : g <= 6 ? "Moderate — satellites starting to cluster."
      : "Poor geometry — satellites clustered (e.g. urban canyon), error is inflated.";
    return { verdict, value: g.toFixed(2),
      hr: "GDOP množi grešku mjerenja: konačna greška ≈ GDOP × šum. " + hrTail,
      en: "GDOP multiplies measurement error: final error ≈ GDOP × noise. " + enTail };
  },
  error(f) {
    const e = f.receiver.error_m;
    if (e == null) return null;
    const verdict: Verdict = e < 8 ? "good" : e <= 30 ? "ok" : "bad";
    const hrTail = e < 8 ? "Tipična točnost jednofrekvencijskog GPS-a."
      : e <= 30 ? "Povišeno — geometrija, ionosfera ili slabiji sateliti."
      : "Veliko — provjeri napad (spoofing) ili lošu geometriju.";
    const enTail = e < 8 ? "Typical single-frequency GPS accuracy."
      : e <= 30 ? "Elevated — geometry, ionosphere or weaker satellites."
      : "Large — check for an attack (spoofing) or poor geometry.";
    return { verdict, value: e.toFixed(1) + " m",
      hr: "Udaljenost procjene (cyan) od PRAVE pozicije (žuto) — mjerljiva samo u simulatoru; pravi prijemnik je ne zna. " + hrTail,
      en: "Distance from the estimate (cyan) to the TRUE position (yellow) — measurable only in a simulator; a real receiver can't see it. " + enTail };
  },
  nis(f) {
    const r = f.receiver.nis_ratio;
    if (r == null) return null;
    const verdict: Verdict = r >= 0.5 && r <= 2 ? "good" : r <= 3 ? "ok" : "bad";
    const hrTail = r >= 0.5 && r <= 2 ? "≈1 — filtar je zdrav i konzistentan."
      : r < 0.5 ? "nisko — filtar je prekonzervativan (precjenjuje šum)."
      : r <= 3 ? "povišeno — mjerenja odstupaju više nego što filtar očekuje."
      : "visoko — jaki odudarci (kvar/napad) ili loše podešen filtar.";
    const enTail = r >= 0.5 && r <= 2 ? "≈1 — the filter is healthy and consistent."
      : r < 0.5 ? "low — the filter is over-conservative (overestimates noise)."
      : r <= 3 ? "elevated — measurements deviate more than the filter expects."
      : "high — strong outliers (fault/attack) or a mistuned filter.";
    return { verdict, value: r.toFixed(2),
      hr: "NIS/dof mjeri slažu li se mjerenja s očekivanjem filtra (EKF). " + hrTail,
      en: "NIS/dof measures whether measurements match the filter's (EKF) expectation. " + enTail };
  },
  sats(f) {
    const n = f.sats_tracked;
    const verdict: Verdict = n < 4 ? "bad" : n < 6 ? "ok" : "good";
    const hrTail = n < 4 ? "Premalo — nema fixa."
      : n < 6 ? "Taman dovoljno."
      : "Zdravo — višak satelita daje bolju geometriju i provjeru integriteta (RAIM).";
    const enTail = n < 4 ? "Too few — no fix."
      : n < 6 ? "Just enough."
      : "Healthy — extra satellites give better geometry and integrity checking (RAIM).";
    return { verdict, value: `${n}/${f.sats_total}`,
      hr: "Sateliti koji ULAZE u rješenje. Trebaš ≥4 (3 za položaj + 1 za sat prijemnika). " + hrTail,
      en: "Satellites that ENTER the solution. You need ≥4 (3 for position + 1 for the receiver clock). " + enTail };
  },
  clock(f) {
    const c = f.receiver.clock_bias_us;
    return { verdict: "ok", value: c.toFixed(1) + " µs",
      hr: "Pomak sata prijemnika koji je filtar riješio — ČETVRTA nepoznanica uz X, Y, Z. Zato trebaš 4 satelita, ne 3. Već 1 µs greške sata = ~300 m greške udaljenosti.",
      en: "The receiver clock offset the filter solved for — the FOURTH unknown alongside X, Y, Z. That's why you need 4 satellites, not 3. Just 1 µs of clock error = ~300 m of range error." };
  },
};

let terms: Record<string, GlossaryTerm> = {};
let lastFrame: StateFrame | null = null;
let pop: HTMLElement | null = null;

async function load(): Promise<void> {
  try { terms = await api.glossary(getLang()); } catch { terms = {}; }
}

function ensure(): HTMLElement {
  if (!pop) {
    pop = h("div", "info-popover");
    pop.style.display = "none";
    document.body.appendChild(pop);
    pop.addEventListener("mouseleave", hide);
  }
  return pop;
}
function hide(): void { if (pop) pop.style.display = "none"; }

// Sekcija definicije pojma.
function defSection(key: string): HTMLElement | null {
  const info = terms[key] || terms[key.toUpperCase()];
  if (!info) return null;
  const sec = h("div", "info-def");
  sec.appendChild(h("div", "info-term", info.term));
  sec.appendChild(h("div", "info-short", info.short));
  sec.appendChild(h("div", "info-long", info.long));
  if (info.related?.length) {
    const rel = h("div", "info-related");
    rel.appendChild(h("span", "info-related-label", t("related") + ": "));
    rel.appendChild(h("span", undefined, info.related.join(", ")));
    sec.appendChild(rel);
  }
  return sec;
}

// Sekcija tumačenja žive vrijednosti (verdict boji rub).
function liveSection(explainKey: string): { node: HTMLElement; verdict: Verdict } | null {
  if (!lastFrame) return null;
  const ex = EXPLAIN[explainKey]?.(lastFrame);
  if (!ex) return null;
  const sec = h("div", "info-live " + ex.verdict);
  const head = h("div", "info-live-head");
  head.appendChild(h("span", "info-live-eyebrow", t("explain_now")));
  head.appendChild(h("span", "info-live-value", ex.value));
  sec.appendChild(head);
  sec.appendChild(h("div", "info-live-body", getLang() === "hr" ? ex.hr : ex.en));
  return { node: sec, verdict: ex.verdict };
}

function place(target: HTMLElement): void {
  const p = ensure();
  const r = target.getBoundingClientRect();
  p.style.display = "block";
  const top = Math.min(r.bottom + 8, window.innerHeight - p.offsetHeight - 12);
  const left = Math.min(r.left, window.innerWidth - p.offsetWidth - 12);
  p.style.top = `${Math.max(12, top)}px`;
  p.style.left = `${Math.max(12, left)}px`;
}

// Samo definicija (generički [data-term]).
function showTerm(target: HTMLElement, key: string): void {
  const def = defSection(key);
  if (!def) return;
  const p = ensure();
  clear(p);
  p.className = "info-popover";
  p.appendChild(def);
  place(target);
}

// Objedinjeno (telemetrijski [data-info]): definicija + živo tumačenje.
function showInfo(target: HTMLElement, concept: string): void {
  const c = CONCEPTS[concept];
  if (!c) return;
  const p = ensure();
  clear(p);
  p.className = "info-popover";
  let any = false;
  if (c.term) { const d = defSection(c.term); if (d) { p.appendChild(d); any = true; } }
  if (c.explain) { const l = liveSection(c.explain); if (l) { p.appendChild(l.node); any = true; } }
  if (!any) return;
  place(target);
}

export function initInfo(): { setFrame: (f: StateFrame) => void } {
  void load();
  onLangChange(() => void load());

  document.addEventListener("mouseover", (ev) => {
    const el = (ev.target as HTMLElement)?.closest?.("[data-term]") as HTMLElement | null;
    if (el?.dataset.term) showTerm(el, el.dataset.term);
  });
  document.addEventListener("click", (ev) => {
    const info = (ev.target as HTMLElement)?.closest?.("[data-info]") as HTMLElement | null;
    if (info?.dataset.info) { ev.stopPropagation(); showInfo(info, info.dataset.info); return; }
    const term = (ev.target as HTMLElement)?.closest?.("[data-term]") as HTMLElement | null;
    if (term?.dataset.term) showTerm(term, term.dataset.term);
    else if (!(ev.target as HTMLElement)?.closest?.(".info-popover")) hide();
  });

  return { setFrame(f: StateFrame): void { lastFrame = f; } };
}
