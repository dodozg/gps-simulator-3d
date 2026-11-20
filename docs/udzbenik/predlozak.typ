// Predložak udžbenika: stil stranice, naslovi, okviri za vježbe i automatski dodatak s rješenjima.

#let sans = ("Segoe UI", "Arial", "Liberation Sans", "DejaVu Sans")
#let boja-glavna = rgb("#1f4e79")
#let boja-vodjena = rgb("#2e7d32")
#let boja-racunska = rgb("#1565c0")
#let boja-istrazivacka = rgb("#8e24aa")
#let boja-napomena = rgb("#ef6c00")

// ---------------------------------------------------------------- UI oznake
// Natpis gumba/kontrole u aplikaciji, točno kako piše u sučelju.
#let ui(t) = box(
  inset: (x: 3pt, y: 0pt), outset: (y: 2.5pt), radius: 2pt,
  fill: luma(235), stroke: 0.4pt + luma(170),
  text(font: sans, size: 0.82em, t),
)
#let kod(t) = text(font: "DejaVu Sans Mono", size: 0.88em, t)

// ---------------------------------------------------------------- okviri
#let okvir(boja, naslov, tijelo) = block(
  width: 100%, breakable: true, above: 1.1em, below: 1.1em,
  stroke: (left: 2.5pt + boja), fill: boja.lighten(93%),
  inset: (left: 10pt, right: 8pt, top: 7pt, bottom: 8pt),
  [#text(fill: boja, weight: "bold", font: sans, size: 0.85em, naslov)
   #v(-0.3em)
   #tijelo],
)

#let napomena(naslov: "Napomena", tijelo) = okvir(boja-napomena, naslov, tijelo)
#let kljucno(tijelo) = okvir(boja-glavna, "Ključne ideje", tijelo)

// ---------------------------------------------------------------- vježbe
// Tri vrste: vodjena (u web-aplikaciji), racunska (papir / Python), istrazivacka (sandbox).
#let vrste = (
  vodjena: (boja-vodjena, "▶", "vođena, u simulatoru"),
  racunska: (boja-racunska, "✎", "računska"),
  istrazivacka: (boja-istrazivacka, "★", "istraživačka, sandbox"),
)

#let brojac-vjezbi = counter("vjezba")

#let vjezba(vrsta: "vodjena", naslov: none, rjesenje: none, tijelo) = {
  let (boja, znak, opis) = vrste.at(vrsta)
  brojac-vjezbi.step()
  context {
    let pog = counter(heading).get().first()
    let br = brojac-vjezbi.get().first()
    let oznaka = str(pog) + "." + str(br)
    let glava = [#znak Vježba #oznaka#if naslov != none [ — #naslov] #h(0.4em)#text(weight: "regular", size: 0.9em, fill: luma(90))[(#opis)]]
    okvir(boja, glava, tijelo)
    if rjesenje != none {
      [#metadata((oznaka: oznaka, naslov: naslov, rjesenje: rjesenje))<rjesenje>]
    }
  }
}

// Ispis svih rješenja (dodatak A).
#let sva-rjesenja() = context {
  let svi = query(<rjesenje>)
  let zadnje-poglavlje = none
  for m in svi {
    let r = m.value
    let pog = r.oznaka.split(".").first()
    if pog != zadnje-poglavlje {
      zadnje-poglavlje = pog
      let h1 = query(heading.where(level: 1)).filter(h => h.numbering != none and counter(heading).at(h.location()).first() == int(pog))
      if h1.len() > 0 {
        block(above: 1.2em, below: 0.6em, text(weight: "bold", fill: boja-glavna)[Poglavlje #pog — #h1.first().body])
      }
    }
    block(breakable: true, below: 0.8em)[
      #text(weight: "bold")[Vježba #r.oznaka#if r.naslov != none [ — #r.naslov]. ]
      #r.rjesenje
    ]
  }
}

// ---------------------------------------------------------------- slike
#let slika(put, opis, sirina: 92%) = figure(image(put, width: sirina), caption: opis)

// ---------------------------------------------------------------- knjiga
#let knjiga(naslov: "", podnaslov: "", autor: "", datum: "", tijelo) = {
  set document(title: naslov, author: autor)
  set text(lang: "hr", font: "New Computer Modern", size: 10.5pt)
  set par(justify: true, leading: 0.62em, spacing: 0.95em)
  set page(
    paper: "a4",
    margin: (inside: 2.6cm, outside: 2.2cm, top: 2.5cm, bottom: 2.4cm),
    header: context {
      let p = here().page()
      let sljedeci = query(heading.where(level: 1)).filter(h => h.location().page() == p)
      if sljedeci.len() > 0 { return }          // nema zaglavlja na prvoj stranici poglavlja
      let prije = query(selector(heading.where(level: 1)).before(here()))
      if prije.len() == 0 { return }
      let zadnji = prije.last()
      set text(size: 8.5pt, fill: luma(110))
      let lijevo = if zadnji.numbering != none [#counter(heading).at(zadnji.location()).first(). #zadnji.body] else [#zadnji.body]
      if calc.even(p) [#str(p) #h(1fr) #naslov] else [#lijevo #h(1fr) #str(p)]
      v(-0.6em)
      line(length: 100%, stroke: 0.3pt + luma(170))
    },
    footer: context {
      let p = here().page()
      let ovdje = query(heading.where(level: 1)).filter(h => h.location().page() == p)
      if ovdje.len() > 0 { align(center, text(size: 8.5pt, fill: luma(110), str(p))) }
    },
  )

  set heading(numbering: "1.1", supplement: none)
  set smartquote(quotes: (single: ("‚", "’"), double: ("„", "”")))
  set math.equation(supplement: none, numbering: n => {
    let pog = counter(heading).get().first()
    "(" + str(pog) + "." + str(n) + ")"
  })
  set figure(numbering: n => {
    let pog = counter(heading).get().first()
    str(pog) + "." + str(n)
  })
  show figure.caption: set text(size: 9pt)
  show figure: set block(above: 1.2em, below: 1.2em)

  show heading.where(level: 1): it => {
    counter(math.equation).update(0)
    counter(figure.where(kind: image)).update(0)
    counter(figure.where(kind: table)).update(0)
    brojac-vjezbi.update(0)
    pagebreak(weak: true, to: "odd")
    v(2.2cm)
    if it.numbering != none {
      text(size: 13pt, fill: boja-glavna, font: sans, weight: "bold")[Poglavlje #counter(heading).display("1")]
      v(0.2em)
    }
    text(size: 22pt, weight: "bold", fill: boja-glavna, it.body)
    v(0.3em)
    line(length: 100%, stroke: 1pt + boja-glavna)
    v(1.2em)
  }
  show heading.where(level: 2): it => block(above: 1.6em, below: 0.8em,
    text(size: 13pt, weight: "bold", fill: boja-glavna, it))
  show heading.where(level: 3): it => block(above: 1.2em, below: 0.6em,
    text(size: 11pt, weight: "bold", it))

  show link: set text(fill: boja-glavna)
  show raw: set text(font: "DejaVu Sans Mono", size: 8.8pt)
  show raw.where(block: true): it => block(width: 100%, fill: luma(245), inset: 8pt, radius: 2pt, stroke: 0.4pt + luma(210), it)
  set table(stroke: 0.4pt + luma(170), inset: 5pt)
  show table.cell.where(y: 0): set text(weight: "bold")

  // ------------------------------------------------------------ naslovnica
  page(header: none, footer: none, margin: 2.5cm)[
    #v(4cm)
    #text(size: 28pt, weight: "bold", fill: boja-glavna, hyphenate: false, naslov)
    #v(0.4em)
    #text(size: 15pt, fill: luma(60), podnaslov)
    #v(1fr)
    #line(length: 100%, stroke: 1pt + boja-glavna)
    #text(size: 11pt)[#autor #h(1fr) #datum]
  ]
  page(header: none, footer: none, [])

  tijelo
}
