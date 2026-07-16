// GPS učilište — dugoformni vodič "GPS objašnjen (kao da imaš 13 godina)".
// Čitljiv modal s kazalom; sadržaj (Markdown) dolazi iz content/guide.{hr,en}.md
// preko /api/guide. Minimalni Markdown prikaz bez vanjskih ovisnosti (podržava
// naslove #/##/###, odlomke, liste, citate, kod i **podebljano** / `kod`).
// Sadržaj je autorski (povjerljiv), ali svejedno gradimo DOM čvorove (bez innerHTML).
import { api } from "../lib/api";
import { t, getLang, onLangChange } from "../lib/i18n";
import { h, clear } from "../lib/dom";

// Inline: **podebljano** i `kod`. Dodaje tekstualne/element-čvorove u `parent`.
function appendInline(parent: HTMLElement, text: string): void {
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
    const tok = m[0];
    if (tok.startsWith("**")) parent.appendChild(h("strong", undefined, tok.slice(2, -2)));
    else parent.appendChild(h("code", "guide-icode", tok.slice(1, -1)));
    last = m.index + tok.length;
  }
  if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
}

interface TocEntry { id: string; title: string; }

function renderMarkdown(md: string): { nodes: HTMLElement[]; toc: TocEntry[] } {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const nodes: HTMLElement[] = [];
  const toc: TocEntry[] = [];
  let i = 0;
  let sec = 0;
  let para: string[] = [];
  const flushPara = (): void => {
    if (para.length) { const p = h("p", "guide-p"); appendInline(p, para.join(" ")); nodes.push(p); para = []; }
  };

  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {                    // kod-blok
      flushPara();
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) { buf.push(lines[i]); i++; }
      i++;                                           // zatvarajuća ograda
      const pre = h("pre", "guide-code");
      pre.appendChild(h("code", undefined, buf.join("\n")));
      nodes.push(pre);
      continue;
    }
    if (/^#\s/.test(line)) { flushPara(); nodes.push(h("h1", "guide-h1", line.slice(2).trim())); i++; continue; }
    if (/^##\s/.test(line)) {
      flushPara();
      sec++;
      const id = `guide-sec-${sec}`;
      const title = line.slice(3).trim();
      const el = h("h2", "guide-h2", title);
      el.id = id;
      nodes.push(el);
      toc.push({ id, title });
      i++;
      continue;
    }
    if (/^###\s/.test(line)) { flushPara(); nodes.push(h("h3", "guide-h3", line.slice(4).trim())); i++; continue; }
    if (line.startsWith("> ")) {
      flushPara();
      const q = h("blockquote", "guide-quote");
      appendInline(q, line.slice(2).trim());
      nodes.push(q);
      i++;
      continue;
    }
    if (/^[*-]\s/.test(line)) {                       // neuređena lista
      flushPara();
      const ul = h("ul", "guide-ul");
      while (i < lines.length && /^[*-]\s/.test(lines[i])) {
        const li = h("li");
        appendInline(li, lines[i].replace(/^[*-]\s/, ""));
        ul.appendChild(li);
        i++;
      }
      nodes.push(ul);
      continue;
    }
    if (/^\d+\.\s/.test(line)) {                       // uređena lista
      flushPara();
      const ol = h("ol", "guide-ol");
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        const li = h("li");
        appendInline(li, lines[i].replace(/^\d+\.\s/, ""));
        ol.appendChild(li);
        i++;
      }
      nodes.push(ol);
      continue;
    }
    if (line.trim() === "") { flushPara(); i++; continue; }
    para.push(line.trim());
    i++;
  }
  flushPara();
  return { nodes, toc };
}

export function mountGuide(): { open: () => void } {
  const overlay = h("div", "guide-overlay");
  overlay.style.display = "none";
  const card = h("div", "guide-card");
  overlay.appendChild(card);
  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) hide(); });

  let loaded = false;
  let servedLang = "";
  let md = "";

  async function ensureLoaded(): Promise<void> {
    try { const r = await api.guide(getLang()); md = r.md; servedLang = r.lang; }
    catch { md = ""; servedLang = getLang(); }
    loaded = true;
  }
  onLangChange(() => { loaded = false; if (overlay.style.display !== "none") void reopen(); });

  function render(): void {
    clear(card);
    const head = h("div", "guide-head");
    head.appendChild(h("span", "guide-title", t("guide_title")));
    const close = h("button", "modal-close", "×");
    close.addEventListener("click", hide);
    head.appendChild(close);
    card.appendChild(head);

    if (!md) { card.appendChild(h("div", "guide-p", "—")); return; }
    if (servedLang !== getLang()) card.appendChild(h("div", "guide-note", t("guide_lang_fallback")));

    const { nodes, toc } = renderMarkdown(md);
    if (toc.length) {
      const nav = h("nav", "guide-toc");
      nav.appendChild(h("div", "guide-toc-title", t("guide_contents")));
      for (const s of toc) {
        const a = h("button", "guide-toc-link", s.title);
        a.addEventListener("click", () =>
          document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" }));
        nav.appendChild(a);
      }
      card.appendChild(nav);
    }
    const content = h("div", "guide-content");
    for (const n of nodes) content.appendChild(n);
    card.appendChild(content);
  }

  function hide(): void { overlay.style.display = "none"; }
  async function reopen(): Promise<void> { await ensureLoaded(); render(); card.scrollTop = 0; }

  return {
    async open(): Promise<void> {
      overlay.style.display = "flex";
      if (!loaded) { clear(card); card.appendChild(h("div", "guide-title", t("guide_title"))); await ensureLoaded(); }
      render();
      card.scrollTop = 0;
    },
  };
}
