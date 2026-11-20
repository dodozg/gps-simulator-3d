# Udžbenik: Satelitska navigacija u simulatoru

PDF: [`Satelitska_navigacija_u_simulatoru.pdf`](Satelitska_navigacija_u_simulatoru.pdf)

Udžbenik za studente tehnike (hrvatski) s vježbama u GPS Simulatoru 3D. Vizualni jezik
(fontovi, boje, naslovnica) preuzet je iz knjige *Od vozača do mehaničara*. Pisan u
[Typstu](https://typst.app); slike i sve brojke u tekstu računa sam simulator.

## Izgradnja

```bash
pip install typst matplotlib                 # uz ovisnosti simulatora (requirements.txt)
python docs/udzbenik/build.py                # PDF iz postojećih slika i brojki
python docs/udzbenik/build.py --slike        # ponovno izračunaj sve slike (nekoliko minuta)
python docs/udzbenik/build.py --slike 07     # samo slike poglavlja 7
python docs/udzbenik/skripte/studije.py      # ponovno odvrti sandbox studije (desetak minuta)
```

## Struktura

| Put | Sadržaj |
|---|---|
| `udzbenik.typ` | glavna datoteka (redoslijed poglavlja) |
| `predlozak.typ` | stil stranice, okviri za vježbe (`#vjezba`), automatski dodatak s rješenjima, `#br()` za brojke |
| `poglavlja/NN-*.typ` | poglavlja; svako čita svoje brojke iz `skripte/brojke_NN.json` |
| `skripte/slike_NN.py` | računa slike (`slike/*.svg`) i brojke poglavlja NN iz simulatora (fiksna sjemena) |
| `skripte/studije.py` | sandbox studije koje knjiga citira → `studije/rezultati/` |
| `studije/*.json`, `primjeri/` | specifikacije studija; primjer plugina (`plugin_ls.py`) |
| `podaci/` | podaci za računske vježbe (izvezeni iz simulatora) |
| `fontovi/` | Source Serif 4, Barlow, Barlow Condensed, JetBrains Mono (OFL, licence uz fontove) |
| `skripte/slike_00_naslovnica.py` | crta ilustraciju naslovnice (pseudoudaljenosti u mreži su iz simulatora) |

## Pravila pisanja

- Brojke iz simulacije nikad se ne upisuju ručno: skripta ih zapiše u `brojke_NN.json`, a
  tekst ih čita s `#br(B.kljuc)`. Promjena modela → `build.py --slike` → nova knjiga.
- U formulama se decimalni zarez piše `2,5`; `build.py` ga sam pretvara u Typstov `2","5`
  (inače bi bio razmak), a `„…"` u `„…”`. Znak `~` je u Typstu tvrdi razmak — piši „oko“ ili ≈.
- Natpisi gumba pišu se `#ui("…")` točno kako ih prikazuje hrvatsko sučelje.
