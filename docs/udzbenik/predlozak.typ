// Predložak udžbenika „Satelitska navigacija u simulatoru”.
// Vizualni jezik preuzet iz knjige „Od vozača do mehaničara”: Source Serif 4 za tekst,
// Barlow Condensed za naslove, Barlow za oznake, JetBrains Mono za kod; petrolej i
// signalno narančasta. Fontovi su u docs/udzbenik/fontovi (OFL), build.py ih predaje Typstu.

// Studentsko izdanje (bez Priloga s rješenjima): typst ... --input rjesenja=ne (build.py ga gradi uz glavno).
#let s-rjesenjima = sys.inputs.at("rjesenja", default: "da") != "ne"

// ---------------------------------------------------------------- boje i fontovi
#let petrol = rgb("#0e4f63")
#let signal = rgb("#c2570a")
#let zelena = rgb("#2c6e49")
#let ink = rgb("#16222b")
#let muted = rgb("#55656f")
#let crta = rgb("#cbd5da")
#let tint = rgb("#eef3f5")
#let signal-tint = rgb("#fdf1e6")
#let zelena-tint = rgb("#ebf4ee")
#let kod-bg = rgb("#f1f4f6")

#let f-tekst = ("Source Serif 4", "New Computer Modern")
#let f-naslov = ("Barlow", "Arial")   // Barlow Condensed: Typst ga vodi kao „Barlow” sa stretch 75 %
#let f-oznaka = ("Barlow", "Arial")
#let f-kod = ("JetBrains Mono", "DejaVu Sans Mono")

// stari nazivi (koriste ih poglavlja)
#let boja-glavna = petrol
#let sans = f-oznaka

// ---------------------------------------------------------------- sitni elementi
// Natpis gumba/kontrole u aplikaciji, točno kako piše u sučelju.
#let ui(t) = box(
  inset: (x: 3pt, y: 0pt), outset: (y: 2.4pt), radius: 2pt,
  fill: tint, stroke: 0.5pt + crta,
  text(font: f-oznaka, size: 0.8em, fill: ink, t),
)
#let kod(t) = box(fill: kod-bg, inset: (x: 2pt), outset: (y: 1.6pt), radius: 1.5pt,
  text(font: f-kod, size: 0.82em, fill: ink, t))
#let cip(t, boja) = box(fill: boja, inset: (x: 4pt, y: 0pt), outset: (y: 2.2pt), radius: 1.5pt,
  text(font: f-oznaka, size: 6.8pt, weight: "bold", fill: white, tracking: 0.06em, upper(t)))

// ---------------------------------------------------------------- brojke iz simulatora
// Broj s hrvatskim decimalnim zarezom i razmakom za tisuće: br(1325732.9, d: 0) -> "1 325 733".
#let br(x, d: 1) = {
  let r = calc.round(float(x), digits: d)
  let neg = r < 0
  let a = calc.abs(r)
  let cijeli = calc.floor(a)
  let s = str(cijeli)
  let grupe = ()
  while s.len() > 3 { grupe.insert(0, s.slice(s.len() - 3)); s = s.slice(0, s.len() - 3) }
  grupe.insert(0, s)
  let out = grupe.join(sym.space.thin)
  if d > 0 {
    let dec = str(calc.round((a - cijeli) * calc.pow(10, d)))
    while dec.len() < d { dec = "0" + dec }
    if dec.len() > d { out = str(cijeli + 1); dec = "0" * d }
    out = out + "," + dec
  }
  if neg { "−" + out } else { out }
}

// ---------------------------------------------------------------- okviri
#let okvir(boja, naslov, tijelo, lomljiv: true, pozadina: none) = block(
  width: 100%, breakable: lomljiv, above: 1.2em, below: 1.2em,
  stroke: (left: 2pt + boja), fill: if pozadina == none { tint } else { pozadina },
  inset: (left: 11pt, right: 10pt, top: 8pt, bottom: 9pt),
  {
    set text(font: f-oznaka, size: 9.2pt)
    set par(justify: false, leading: 0.6em)
    if naslov != none {
      block(below: 0.55em, text(font: f-naslov, stretch: 75%, size: 11.5pt, weight: "semibold", fill: boja, naslov))
    }
    tijelo
  },
)

#let napomena(naslov: "Napomena", tijelo) = okvir(petrol, naslov, tijelo, lomljiv: false)
#let kljucno(tijelo) = okvir(signal, "Ključne ideje", tijelo, lomljiv: false, pozadina: signal-tint)

// Ciljevi poglavlja, odmah ispod naslova (kao „Nakon ovog poglavlja znaš:”).
#let cilj(..stavke) = block(width: 100%, above: 0.2em, below: 1.6em, inset: (bottom: 10pt),
  stroke: (bottom: 0.5pt + crta), {
    set text(font: f-oznaka, size: 8.8pt, fill: ink)
    set par(justify: false, leading: 0.5em)
    text(weight: "bold")[Nakon ovog poglavlja znaš:]
    v(0.25em)
    for s in stavke.pos() {
      block(above: 0.35em, below: 0em, grid(columns: (9pt, 1fr), text(fill: signal)[■], s))
    }
  })

// ---------------------------------------------------------------- vježbe
// Tri vrste: vodjena (u web-aplikaciji), racunska (papir / Python), istrazivacka (sandbox).
#let vrste = (
  vodjena: (petrol, "simulator"),
  racunska: (zelena, "račun"),
  istrazivacka: (signal, "sandbox"),
)
#let brojac-vjezbi = counter("vjezba")

#let vjezba(vrsta: "vodjena", naslov: none, rjesenje: none, tijelo) = {
  let (boja, oznaka-vrste) = vrste.at(vrsta)
  brojac-vjezbi.step()
  context {
    let pog = counter(heading).get().first()
    let n = brojac-vjezbi.get().first()
    let oznaka = str(pog) + "." + str(n)
    let glava = [Vježba #oznaka#if naslov != none [: #naslov] #h(0.35em) #cip(oznaka-vrste, boja)]
    okvir(boja, glava, tijelo, lomljiv: false)
    if rjesenje != none {
      [#metadata((oznaka: oznaka, naslov: naslov, rjesenje: rjesenje, vrsta: vrsta))<rjesenje>]
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
        block(above: 1.4em, below: 0.6em, sticky: true, text(font: f-naslov, stretch: 75%, size: 13pt, weight: "semibold", fill: petrol)[
          #text(fill: signal, weight: "regular")[#pog] #h(0.3em) #h1.first().body])
      }
    }
    let (boja, _) = vrste.at(r.at("vrsta", default: "vodjena"))
    block(breakable: true, below: 0.75em)[
      #text(font: f-oznaka, weight: "bold", fill: boja)[Vježba #r.oznaka#if r.naslov != none [: #r.naslov]. ]
      #r.rjesenje
    ]
  }
}

// Mali nadnaslov iznad sljedećeg nenumeriranog naslova poglavlja (npr. „Prilog A”).
#let nadnaslov-stanje = state("nadnaslov", none)
#let nadnaslov(t) = nadnaslov-stanje.update(t)

// ---------------------------------------------------------------- dijelovi knjige
#let dio(broj, naslov, opis, poglavlja: ()) = {
  pagebreak(weak: true)
  [#metadata((broj: broj, naslov: naslov))<dio>]
  page(footer: none, header: none, {
    v(1fr)
    text(font: f-naslov, stretch: 75%, size: 12pt, weight: "semibold", fill: signal, tracking: 0.12em)[DIO #broj]
    v(0.2em)
    block(text(font: f-naslov, stretch: 75%, size: 40pt, weight: "bold", fill: petrol, hyphenate: false, naslov))
    v(0.4em)
    block(width: 80%, text(font: f-oznaka, size: 11pt, fill: muted, opis))
    v(1.4em)
    line(length: 100%, stroke: 0.8pt + petrol)
    v(0.6em)
    for (b, n) in poglavlja {
      block(above: 0.5em, text(font: f-oznaka, size: 10.5pt, fill: ink)[
        #box(width: 2em, text(font: f-naslov, stretch: 75%, weight: "semibold", fill: signal, str(b))) #n])
    }
    v(1.3fr)
  })
}

// ---------------------------------------------------------------- sadržaj
#let sadrzaj() = {
  pagebreak(weak: true)
  block(below: 1.2em, text(font: f-naslov, stretch: 75%, size: 30pt, weight: "bold", fill: petrol)[Sadržaj])
  context {
    let stavke = query(selector(<dio>).or(heading.where(level: 1))).filter(e => e.func() == metadata or e.outlined)
    set text(font: f-oznaka, size: 10.6pt, fill: ink)
    for e in stavke {
      let loc = e.location()
      let str-br = text(font: f-naslov, stretch: 75%, size: 11.5pt, weight: "semibold", fill: petrol, str(counter(page).at(loc).first()))
      if e.func() == metadata {
        block(above: 1.35em, below: 0.55em, link(loc, grid(columns: (1fr, auto),
          text(font: f-naslov, stretch: 75%, size: 14pt, weight: "bold", fill: petrol)[#text(fill: signal)[Dio #e.value.broj] #h(0.3em) #e.value.naslov], str-br)))
      } else {
        let broj = if e.numbering != none { str(counter(heading).at(loc).first()) } else { "" }
        block(above: 0.62em, below: 0em, link(loc, grid(columns: (2.1em, 1fr, auto),
          text(font: f-naslov, stretch: 75%, size: 11.5pt, weight: "semibold", fill: signal, broj), e.body, str-br)))
      }
    }
  }
}

// ---------------------------------------------------------------- slike
#let slika(put, opis, sirina: 92%) = figure(image(put, width: sirina), caption: opis)

// ---------------------------------------------------------------- naslovnica
#let naslovnica(naslov, podnaslov, autor, izdanje) = page(margin: 0pt, header: none, footer: none, {
  place(top + left, dx: 24mm, dy: 46mm, block(width: 162mm, {
    text(font: f-naslov, stretch: 75%, size: 11pt, weight: "semibold", fill: signal, tracking: 0.14em)[UDŽBENIK S VJEŽBAMA U SIMULATORU]
    v(0.6em)
    block(text(font: f-naslov, stretch: 75%, size: 56pt, weight: "bold", fill: petrol, hyphenate: false, top-edge: "cap-height")[#par(leading: 0.08em, naslov)])
    v(1.1em)
    block(width: 128mm, text(font: f-oznaka, size: 13pt, fill: muted, hyphenate: false, podnaslov))
    v(1.1em)
    text(font: f-naslov, stretch: 75%, size: 14pt, weight: "semibold", fill: petrol, autor)
  }))
  place(bottom + left, image("slike/naslovnica.svg", width: 100%))
  place(bottom + left, dx: 22mm, dy: -9mm, block(fill: white, inset: (x: 3pt, y: 2pt), text(font: f-oznaka, size: 7.5pt, fill: muted, izdanje)))
})

// ---------------------------------------------------------------- knjiga
#let knjiga(naslov: "", podnaslov: "", autor: "", izdanje: "", tijelo) = {
  set document(title: "Satelitska navigacija u simulatoru", author: ("Domagoj Zoričić", "Claude (Anthropic)"))
  set text(lang: "hr", font: f-tekst, size: 10.2pt, fill: ink, number-type: "lining")
  set par(justify: true, leading: 0.68em, spacing: 1.05em)
  show math.equation: set text(font: ("New Computer Modern Math",))
  set page(
    paper: "a4",
    margin: (x: 25mm, top: 24mm, bottom: 26mm),
    footer: context {
      let p = here().page()
      let prije = query(selector(heading.where(level: 1)).before(here()))
      let naslov-pogl = if prije.len() == 0 { "" } else {
        let h = prije.last()
        if h.numbering != none [#counter(heading).at(h.location()).first(). #h.body] else [#h.body]
      }
      line(length: 100%, stroke: 0.4pt + crta)
      v(-0.3em)
      grid(columns: (1fr, auto),
        text(font: f-oznaka, size: 7.5pt, fill: muted, naslov-pogl),
        text(font: f-naslov, stretch: 75%, size: 10.5pt, weight: "semibold", fill: petrol, str(counter(page).get().first())))
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
  show figure.caption: it => {
    set text(font: f-oznaka, size: 8.4pt, fill: muted)
    set par(justify: false, leading: 0.5em)
    block(width: 92%, [#text(weight: "bold", fill: petrol)[#it.supplement #context it.counter.display(it.numbering).] #it.body])
  }
  show figure: set block(above: 1.4em, below: 1.4em)
  show figure.where(kind: table): set figure.caption(position: top)

  show heading: set par(justify: false)
  show heading: set text(hyphenate: false)
  show heading.where(level: 1): it => {
    counter(math.equation).update(0)
    counter(figure.where(kind: image)).update(0)
    counter(figure.where(kind: table)).update(0)
    brojac-vjezbi.update(0)
    pagebreak(weak: true)
    v(6mm)
    if it.numbering != none {
      block(below: 0.1em, text(font: f-naslov, stretch: 75%, size: 58pt, weight: "light", fill: signal, top-edge: "cap-height",
        counter(heading).display("1")))
    } else {
      context {
        let nn = nadnaslov-stanje.get()
        if nn != none {
          block(below: 0.4em, text(font: f-naslov, stretch: 75%, size: 11pt, weight: "semibold", fill: signal, tracking: 0.12em, upper(nn)))
        }
      }
      nadnaslov-stanje.update(none)
    }
    block(below: 0.5em, text(font: f-naslov, stretch: 75%, size: 30pt, weight: "bold", fill: petrol, it.body))
    line(length: 100%, stroke: 1.2pt + petrol)
    v(0.7em)
  }
  show heading.where(level: 2): it => block(above: 1.7em, below: 0.75em, sticky: true, {
    set text(font: f-naslov, stretch: 75%, size: 15.5pt, weight: "semibold", fill: petrol)
    if it.numbering != none { text(fill: signal, weight: "regular", counter(heading).display()) ; h(0.45em) }
    it.body
  })
  show heading.where(level: 3): it => block(above: 1.3em, below: 0.6em, sticky: true,
    text(font: f-oznaka, size: 10.5pt, weight: "bold", fill: ink, it.body))

  show link: set text(fill: petrol)
  show ref: set text(fill: petrol)
  show raw: set text(font: f-kod, size: 8.2pt)
  show raw.where(block: true): it => block(width: 100%, fill: kod-bg, inset: (x: 10pt, y: 8pt),
    stroke: (left: 2pt + crta), it)
  show list: set list(marker: text(fill: signal, size: 0.75em, baseline: -0.1em)[■], indent: 0.2em, body-indent: 0.6em)
  show enum: set enum(numbering: n => text(font: f-naslov, stretch: 75%, weight: "semibold", fill: signal, str(n) + "."))

  set table(stroke: (x, y) => if y == 0 { (bottom: 0.9pt + petrol) } else { (bottom: 0.4pt + crta) },
    inset: (x: 6pt, y: 4.5pt))
  show table: set text(font: f-oznaka, size: 8.8pt, number-type: "lining", number-width: "tabular")
  show table.cell.where(y: 0): set text(weight: "semibold", fill: petrol)

  naslovnica(naslov, podnaslov, autor, izdanje)
  tijelo
}
