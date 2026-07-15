// "Objasni ovo" — kontekstualna objašnjenja ŽIVIH vrijednosti. Za razliku od
// pojmovnika (što pojam JEST), ovo tumači što TRENUTNI broj znači: npr. "GDOP je
// 2.3 — dobra geometrija" vs ">6 bio bi loš". Klik na vrijednost otvori popover.
import type { StateFrame } from "../lib/types";
import { t, getLang } from "../lib/i18n";
import { h, clear } from "../lib/dom";

type Verdict = "good" | "ok" | "bad";
interface Ex { verdict: Verdict; value: string; hr: string; en: string; }

// Tumači po ključu — svaki čita trenutni frame i vraća ocjenu + dvojezični tekst.
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

export function mountExplain() {
  let last: StateFrame | null = null;
  let pop: HTMLElement | null = null;

  function ensure(): HTMLElement {
    if (!pop) {
      pop = h("div", "explain-popover");
      pop.style.display = "none";
      document.body.appendChild(pop);
    }
    return pop;
  }
  function hide(): void { if (pop) pop.style.display = "none"; }

  function show(target: HTMLElement, key: string): void {
    if (!last) return;
    const fn = EXPLAIN[key];
    const ex = fn ? fn(last) : null;
    if (!ex) return;
    const p = ensure();
    clear(p);
    p.className = "explain-popover " + ex.verdict;
    const head = h("div", "explain-head");
    head.appendChild(h("span", "explain-eyebrow", t("explain_this")));
    head.appendChild(h("span", "explain-value", ex.value));
    p.appendChild(head);
    p.appendChild(h("div", "explain-body", getLang() === "hr" ? ex.hr : ex.en));
    const r = target.getBoundingClientRect();
    p.style.display = "block";
    const top = Math.min(r.bottom + 8, window.innerHeight - p.offsetHeight - 12);
    const left = Math.min(r.left, window.innerWidth - p.offsetWidth - 12);
    p.style.top = `${Math.max(12, top)}px`;
    p.style.left = `${Math.max(12, left)}px`;
  }

  document.addEventListener("click", (ev) => {
    const el = (ev.target as HTMLElement)?.closest?.("[data-explain]") as HTMLElement | null;
    if (el?.dataset.explain) { ev.stopPropagation(); show(el, el.dataset.explain); }
    else if (!(ev.target as HTMLElement)?.closest?.(".explain-popover")) hide();
  });

  return { setFrame(f: StateFrame): void { last = f; } };
}
