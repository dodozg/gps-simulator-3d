#import "../predlozak.typ": *
#set heading(numbering: none)

#heading(numbering: none, outlined: false)[Predgovor]

Satelitska navigacija je jedna od rijetkih tehnologija koju gotovo svatko koristi svaki dan, a gotovo nitko ne vidi kako radi. Telefon pokaže plavu točku na karti. Iza nje stoje atomski satovi u orbiti, signali slabiji od toplinskog šuma, korelatori, nelinearni procjenitelji i statistički testovi koji odlučuju smije li se toj točki vjerovati.

Ova knjiga prolazi taj lanac od signala do integriteta. Posebna je po tome što je svaki pojam vezan uz *živi simulator*. GPS Simulator 3D nije animacija: u njemu se pseudoudaljenosti stvarno računaju, na njih se nanose fizikalno modelirane pogreške, a položaj se rješava istim algoritmima kao u pravom prijemniku (najmanji kvadrati, Kalmanov filtar, RAIM, RTK). Budući da je riječ o simulaciji, uvijek je poznata i *istina*. Zato se može izmjeriti nešto što pravi prijemnik nikad ne zna: koliko je pogriješio i zašto.

Knjiga je namijenjena studentima tehničkih fakulteta na prvom kolegiju satelitske navigacije, ali i inženjerima koji žele brzo i konkretno razumjeti GNSS. Pretpostavlja se poznavanje linearne algebre (matrice, inverz, najmanji kvadrati u osnovnom obliku), osnova vjerojatnosti (Gaussova razdioba, varijanca) i osnovno programiranje u Pythonu. Sve ostalo se izvodi u tekstu.

#heading(numbering: none)[Kako koristiti knjigu]

== Struktura

Poglavlja 1–5 grade model mjerenja: što je GNSS, u kojim koordinatama i vremenskim skalama radi, kako se gibaju sateliti, kako izgleda signal i koje se pogreške uvlače u pseudoudaljenost. Poglavlja 6–8 rješavaju položaj: najmanji kvadrati, geometrija i DOP, Kalmanov filtar. Poglavlja 9–12 proširuju sliku: više sustava, integritet, fazna mjerenja s centimetarskom točnošću te namjerno ometanje i lažiranje. Poglavlje 13 prelazi s simulacije na prave podatke iz RINEX datoteka. Poglavlje 14 daje istraživačke projekte za samostalan rad. Rješenja svih vježbi su u dodatku.

== Tri vrste vježbi

#okvir(boja-vodjena, [▶ Vođena vježba (u simulatoru)])[
  Radi se u web-aplikaciji: postaviš prijemnik, nešto promijeniš i promatraš. Natpisi gumba i kontrola napisani su #ui("ovako"), točno kako ih prikazuje sučelje na hrvatskom. Odgovor je opažanje uz objašnjenje.
]
#okvir(boja-racunska, [✎ Računska vježba])[
  Izvod na papiru ili kratki program u Pythonu. Podaci koje vježbe koriste su u mapi #kod("docs/udzbenik/podaci/") i izvezeni su iz simulatora.
]
#okvir(boja-istrazivacka, [★ Istraživačka vježba (sandbox)])[
  Statistička studija u istraživačkom sandboxu: rešetka parametara × Monte Carlo preko sjemena × više algoritama, s intervalima pouzdanosti. Odgovor nije jedan broj nego trend i njegova pouzdanost.
]

Sve brojke u tekstu i rješenjima (pogreške, DOP-ovi, vremena konvergencije) *izračunate su simulatorom*. Skripte koje ih računaju su u #kod("docs/udzbenik/skripte/") i koriste fiksna sjemena, pa je knjiga reproducibilna. Tvoji rezultati u živoj aplikaciji razlikovat će se u detaljima, jer ovise o trenutku i mjestu na kojem postaviš prijemnik, ali ne u redu veličine ni u trendovima.

== Pokretanje simulatora

Simulator je projekt otvorenog koda (#link("https://github.com/dodozg/gps-simulator-3d")[github.com/dodozg/gps-simulator-3d]). Za vježbe trebaš Python 3.11 ili noviji i, za web-sučelje, Node.js 20.19+.

```
git clone https://github.com/dodozg/gps-simulator-3d
cd gps-simulator-3d
setup.bat            # Windows (macOS/Linux: ./setup.sh) — virtualno okruženje i ovisnosti
build_web.bat        # jednom: izgradi web-sučelje (macOS/Linux: ./build_web.sh)
run_webapp.bat       # pokreni (macOS/Linux: ./run_webapp.sh), pa otvori http://localhost:8010
```

Alati bez sučelja pokreću se izravno, npr. #kod("python sandbox.py list") ili #kod("python realdata.py --help").

== Snalaženje u aplikaciji

Sredinom zaslona je 3D globus. *Dvoklik* na globus postavlja prijemnik, čija se visina uzima iz stvarnog modela terena. Traka #ui("Leti do grada ili koordinata…") iznad globusa vodi do zadanog mjesta. U zaglavlju se biraju jezik (HR/EN) i razina prikaza: #ui("Početnik") ili #ui("Stručnjak"). Za vježbe u ovoj knjizi uključi #ui("Stručnjak"), jer tek tada telemetrija prikazuje NIS, ISB, statistiku testa RAIM-a i ostale međuveličine.

- *Lijevi panel*, #ui("Kontrole"): #ui("Pokreni") / #ui("Pauza"), #ui("Brzina") simulacije, #ui("Poništi"), prekidači #ui("Kinematički (let)"), #ui("RAIM integritet"), #ui("RTK (fazni, cm)"), klizač #ui("Doba dana (ionosfera)"), #ui("Napad"), izvor #ui("Orbite") (#ui("Idealizirane (Walker)") ili #ui("Prave (CelesTrak)")), panel #ui("Sustavi") (GPS, Galileo, GLONASS, BeiDou) te gumbi za #ui("Eksperimenti…"), #ui("Vođene lekcije…"), #ui("Kako radi GPS?") i #ui("Pogled iznutra (matematika epohe)…").
- *Desni panel*, #ui("Telemetrija"): istina i procjena položaja, #ui("Greška"), GDOP, sat prijemnika, #ui("Integritet") i #ui("Zaštitna granica") te tablica #ui("Sateliti u vidokrugu") (elevacija, azimut, status, rezidual, C/N0). Klik na redak otvara *editor satelita*, u kojem se satelitu mogu ubrizgati kvar sata, pomak pozicije ili promjena snage. Pojmovi u plavoj boji su klikabilni i otvaraju definiciju.
- *Donji dok*, #ui("Živi grafovi"): pogreška, GDOP i NIS kroz vrijeme te #ui("Skyplot (uživo)").

#napomena(naslov: "Sigurna početna točka")[
  Ako se nešto „” (ugašeni sateliti, aktivan napad, čudna orbita), #ui("Poništi") vraća simulaciju u početno stanje. Lokacija prijemnika se pamti i nakon ponovnog pokretanja servera.
]
