#import "../predlozak.typ": *
#let B = json("../skripte/brojke_01.json")

= Uvod u satelitsku navigaciju <pog:gnss>

Globalni navigacijski satelitski sustavi (GNSS, _Global Navigation Satellite Systems_) omogućuju svakom prijemniku na Zemlji ili blizu nje da u svakom trenutku, po bilo kojem vremenu i bez slanja ijednog signala odredi svoj položaj, brzinu i točno vrijeme. Ovo poglavlje daje osnovnu ideju i rječnik koji koristimo kroz cijelu knjigu te pokazuje što od toga simulator modelira.

== Ideja: udaljenost iz vremena

Satelit emitira signal u koji je utisnut trenutak odašiljanja prema njegovom atomskom satu. Prijemnik zabilježi trenutak prijama svojim satom. Razlika, pomnožena brzinom svjetlosti $c = 299 space 792 space 458 "m/s"$, daje udaljenost. Udaljenost do jednog satelita smješta prijemnik na sferu oko satelita. Tri sfere sijeku se u dvije točke, od kojih je jedna daleko u svemiru, pa bi tri satelita bila dovoljna. Ali samo ako su satovi savršeno usklađeni.

Upravo tu je glavni problem. Signal GPS-satelita u zenitu putuje #br(B.tau_zenit_ms) ms, a satelita blizu horizonta (elevacija 5°) #br(B.tau_5_ms) ms. Pogreška sata od jedne nanosekunde je pogreška udaljenosti od 30 cm, a od jedne mikrosekunde 300 m. Sateliti nose atomske satove, a prijemnik u telefonu jeftin kvarcni oscilator. Zato se pogreška sata prijemnika ne pokušava izmjeriti, nego se *procjenjuje kao četvrta nepoznanica*, zajedno s tri koordinate. Mjerena veličina stoga nije prava udaljenost, nego *pseudoudaljenost*: udaljenost uvećana za (nepoznatu) pogrešku sata prijemnika. Treba nam barem četiri satelita (pogl. @pog:ls).

#kljucno[
  - GNSS je *pasivan* sustav: korisnik samo prima i zato broj korisnika nije ograničen.
  - Položaj se određuje iz *vremena*. Navigacija je zapravo problem preciznog mjerenja vremena.
  - Četvrti satelit nije luksuz: njime se rješava sat prijemnika.
]

== Tri segmenta

Svaki GNSS sastoji se od tri dijela:

- *Svemirski segment*: sateliti u srednjoj Zemljinoj orbiti (MEO, 19 000–24 000 km), svaki s atomskim satovima, odašiljačem i antenom usmjerenom prema Zemlji. Emitiraju kodirane signale u L-pojasu (oko 1,2–1,6 GHz) i *navigacijsku poruku* s parametrima vlastite orbite (efemeride) i korekcijama sata.
- *Kontrolni segment*: mreža zemaljskih stanica koje prate satelite, računaju njihove orbite i pogreške satova te ih redovito šalju natrag satelitima da ih ovi emitiraju.
- *Korisnički segment*: prijemnici. Prijemnik iz signala mjeri pseudoudaljenosti, iz poruke dekodira gdje je satelit bio u trenutku odašiljanja i rješava položaj.

Kontrolni segment je razlog zašto prijemnik ne mora sam pratiti satelite. Ali i razlog zašto se u mjerenje uvlači pogreška: emitirane efemeride su prognoza s pogreškom reda veličine metra (pogl. @pog:pogreske).

== Četiri globalna sustava

Danas rade četiri globalna sustava. Svi koriste isti princip pseudoudaljenosti, a razlikuju se orbitama, signalima i vlastitom vremenskom skalom:

#figure(
  table(
    columns: (auto, auto, auto, auto, auto),
    align: (left, left, right, right, right),
    [Sustav], [Upravlja], [Visina orbite], [Inklinacija], [U snimci (11/2026)],
    [GPS], [SAD], [20 200 km], [55°], [#B.snimka_po_sustavu.GPS],
    [GLONASS], [Rusija], [19 100 km], [64,8°], [#B.snimka_po_sustavu.GLO],
    [Galileo], [EU], [23 222 km], [56°], [#B.snimka_po_sustavu.GAL],
    [BeiDou], [Kina], [21 500 km (MEO)], [55°], [#B.snimka_po_sustavu.BDS],
  ),
  caption: [Globalni GNSS-ovi. Visine i inklinacije su nazivne (iste koristi idealizirani model simulatora). Zadnji stupac je broj satelita u snimci CelesTrakovih orbitalnih elemenata ugrađenoj u simulator. BeiDou uz MEO ima i geostacionarne i nagnute geosinkrone satelite.],
) <tab:sustavi>

GPS je referentni sustav ove knjige: većina primjera koristi samo njega, a ostali dolaze u poglavlju o multi-GNSS-u (pogl. @pog:multignss). Postoje i regionalni sustavi (japanski QZSS, indijski NavIC) te sustavi za poboljšanje točnosti i integriteta (SBAS, npr. europski EGNOS), koje ova knjiga ne obrađuje.

@fig:vidljivi pokazuje koliko se satelita vidi iz Zagreba kroz jedan dan. S idealiziranim konstelacijama od 24 satelita po sustavu, kakve simulator koristi kad su odabrane #ui("Idealizirane (Walker)") orbite, iznad maske od #B.maska_deg° vidi se #B.vid.w_gps.min–#B.vid.w_gps.max GPS satelita. S pravim orbitama (#ui("Prave (CelesTrak)")) ih je #B.vid.p_gps.min–#B.vid.p_gps.max, jer stvarni GPS ima #B.snimka_po_sustavu.GPS satelita, a ne nazivna 24. Sa sva četiri sustava prosječno je iznad maske #br(B.vid.p_svi.sred, d: 0) satelita.

#figure(
  image("../slike/01-vidljivi-sateliti.svg", width: 96%),
  caption: [Broj satelita iznad elevacije #B.maska_deg° u Zagrebu kroz 24 sata: idealizirane Walker konstelacije (iscrtkano) i prave orbite propagirane modelom SGP4 iz ugrađene snimke (puna linija).],
) <fig:vidljivi>

== Što prijemnik zapravo radi

Put od antene do položaja ima četiri stupnja. Prema njima je organiziran i ostatak knjige:

#let korak(naslov, opis) = box(width: 23%, inset: 6pt, radius: 3pt, stroke: 0.6pt + boja-glavna, fill: boja-glavna.lighten(92%))[
  #set par(justify: false)
  #text(weight: "bold", size: 9pt, naslov) \ #text(size: 8pt, opis)
]
#align(center, block(width: 100%)[
  #korak([Signal], [akvizicija i praćenje koda, C/N0 (pogl. 4)])
  #h(1fr) → #h(1fr)
  #korak([Pseudoudaljenosti], [modeli pogrešaka i korekcije (pogl. 5)])
  #h(1fr) → #h(1fr)
  #korak([Navigacija], [LS, Kalman, DOP (pogl. 6–9)])
  #h(1fr) → #h(1fr)
  #korak([Integritet], [RAIM, HPL, napadi (pogl. 10–12)])
])

Simulator prolazi istim lancem u svakoj epohi. Za svaki satelit iznad horizonta računa jakost signala i provjerava drži li ga prijemnik zaključanog. Zatim stvara pseudoudaljenosti na dvije frekvencije s fizikalno modeliranim pogreškama, kombinira ih tako da ukloni ionosferu, primijeni korekcije, riješi položaj Kalmanovim filtrom i provjeri dosljednost mjerenja statističkim testom.

== Mjere kvalitete

Navigacijski sustav ne ocjenjuje se samo točnošću. U zrakoplovstvu (ICAO) i drugdje gdje o položaju ovise životi koriste se četiri mjere:

- *Točnost*: koliko je procijenjeni položaj blizu stvarnog, obično kao 95. percentil (p95) pogreške.
- *Integritet*: sposobnost sustava da *na vrijeme upozori* kad mu se ne smije vjerovati. Opasna situacija nije velika pogreška, nego velika pogreška *bez upozorenja* (pogl. @pog:raim).
- *Kontinuitet*: vjerojatnost da usluga neće biti prekinuta tijekom operacije.
- *Dostupnost*: udio vremena u kojem su prethodna tri zahtjeva zadovoljena.

Simulator mjeri sve četiri, a jednu stvar koju pravi prijemnik nikad ne može: stvarnu pogrešku, jer zna istinu.

== Što simulator modelira, a što ne

Simulator je *pravi navigacijski procesor na simuliranim mjerenjima*. Algoritmi od pseudoudaljenosti naviše (najmanji kvadrati, Kalmanov filtar, RAIM, RTK) su isti kakvi bi radili na stvarnim podacima, što pokazuje poglavlje 13, u kojem isti kod obrađuje prave RINEX datoteke. Pojednostavljenja su na strani stvaranja signala:

- signal se ne stvara kao niz uzoraka, nego se modelira na razini korelatora (C/N0, šum i pristranost petlje koda), pa nema praćenja faze nosioca u kodnom lancu ni navigacijskih bitova;
- svi sustavi koriste kod nalik GPS-ovom C/A kodu, iako stvarni Galileo, GLONASS i BeiDou imaju drukčije modulacije;
- idealizirane orbite su Keplerove elipse s precesijom zbog spljoštenosti Zemlje (J2) na sfernoj Zemlji polumjera 6371 km. Prave orbite dolaze iz SGP4 propagacije javnih elemenata, točnih na razini kilometra, ali konzistentnih unutar simulacije;
- ionosfera je Klobucharov model, a ne mjerena karta elektronskog sadržaja, a troposfera je jednostavan model s mapiranjem $1 \/ sin "el"$.

Ta pojednostavljenja određuju gdje su granice simulatora. Ne utječu na ono što knjiga želi pokazati: kako se iz nesavršenih mjerenja dolazi do položaja i koliko mu se smije vjerovati.

#vjezba(vrsta: "vodjena", naslov: "Prvi pogled", rjesenje: [
  S idealiziranim orbitama i samo GPS-om u tablici je obično 5–8 satelita (@fig:vidljivi). Uključivanjem ostalih sustava broj naraste na 25–35. Pogreška se uz sva četiri sustava u pravilu smanjuje i postaje mirnija, a GDOP osjetno pada (pogl. @pog:dop). Bez pokrenute simulacije sateliti stoje i položaj se ne računa.
])[
  Pokreni aplikaciju, dvoklikom postavi prijemnik na svoj grad i klikni #ui("Pokreni").
  + Koliko je satelita u tablici #ui("Sateliti u vidokrugu") kad je u panelu #ui("Sustavi") uključen samo GPS? Koliko ih se koristi u rješenju (#ui("koristi se"))?
  + Uključi redom Galileo, GLONASS i BeiDou. Kako se mijenjaju broj satelita, #ui("Greška") i GDOP?
  + Pauziraj simulaciju. Što se događa s položajem?
]

#vjezba(vrsta: "vodjena", naslov: "Vođena lekcija", rjesenje: [
  Lekcija pokazuje da s tri satelita (tri sfere) i netočnim satom prijemnika sfere nemaju zajedničko sjecište, a s četvrtim se sat može procijeniti. U simulatoru se to vidi tako da se rješenje bez barem četiri praćena satelita uopće ne računa.
])[
  Otvori #ui("Vođene lekcije…") i prođi lekciju #ui("Zašto trebaš 4 satelita?"). Svojim riječima objasni zašto treći satelit nije dovoljan kad sat prijemnika nije savršen.
]

#vjezba(vrsta: "racunska", naslov: "Koliko daleko i koliko dugo", rjesenje: [
  (a) U zenitu je udaljenost jednaka visini orbite, #br(B.d_zenit_km, d: 0) km, a vrijeme leta #br(B.tau_zenit_ms) ms. (b) Iz kosinusovog poučka za trokut središte Zemlje–prijemnik–satelit: $d = sqrt(r_s^2 - R^2 cos^2 "el") - R sin "el"$, uz $R = 6371$ km i $r_s = R + 20 space 200$ km. Za el = 5° dobivamo $d approx$ #br(B.d_5_km, d: 0) km i #br(B.tau_5_ms) ms. (c) $c dot 1 "ns" approx$ #br(B.m_po_ns, d: 1) m, pa za 3 m treba sat točan na 10 ns, a za 30 cm na 1 ns. Kvarcni sat u telefonu ima drift reda veličine $10^(-6)$, pa za jednu sekundu odluta 1 µs, tj. 300 m. Zato se sat mora procjenjivati.
])[
  Za GPS satelit na visini 20 200 km iznad sferne Zemlje polumjera 6371 km izračunaj:
  + udaljenost i vrijeme leta signala kad je satelit u zenitu;
  + udaljenost i vrijeme leta kad je satelit na elevaciji 5° (nacrtaj trokut središte Zemlje–prijemnik–satelit);
  + koliko točan mora biti sat da pogreška udaljenosti bude manja od 3 m, odnosno od 30 cm. Koliko bi kvarcni sat s relativnom pogreškom frekvencije $10^(-6)$ odlutao u jednoj sekundi?
]

#vjezba(vrsta: "vodjena", naslov: "Prave orbite", rjesenje: [
  S pravim orbitama u tablici je s GPS-om obično 7–12 satelita, više nego u idealiziranom modelu, jer stvarni GPS ima #B.snimka_po_sustavu.GPS satelita. Oznake satelita postaju stvarne (npr. G22, E101, R720, C04). Na globusu se vidi da prave orbite nisu savršeno pravilno raspoređene, a BeiDou ima i satelite koji stoje iznad ekvatora (geostacionarni).
])[
  U lijevom panelu u odjeljku #ui("Orbite") promijeni #ui("Izvor") na #ui("Prave (CelesTrak)") i klikni #ui("Sada").
  + Koliko se sada vidi GPS satelita? Usporedi s @fig:vidljivi.
  + Kako su satelitima sada označeni identifikatori?
  + Uključi BeiDou i promotri globus. Vidiš li satelite koji se ne pomiču u odnosu na Zemlju? Gdje su?
]
