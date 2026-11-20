#import "../predlozak.typ": *
#let B = json("../skripte/brojke_07.json")
#let MS = B.studija_max_sats
#let MK = B.studija_maska
#let nadji(niz, x) = niz.filter(p => p.x == x).first()

= Geometrija i DOP <pog:dop>


#cilj(
  [izračunati DOP-ove iz matrice geometrije],
  [zašto je pogreška položaja približno DOP puta pogreška mjerenja],
  [zašto je visina gotovo uvijek lošija od položaja u ravnini],
  [kako broj satelita i maska elevacije mijenjaju točnost],
)

Dva prijemnika s jednako dobrim mjerenjima mogu imati vrlo različitu točnost samo zato što vide satelite raspoređene na različite načine. Ovo poglavlje pokazuje kako matrica geometrije $bold(G)$ iz poglavlja @pog:ls određuje koliko se pogreška mjerenja pojača u pogrešku položaja. Ta se veličina zove DOP (_dilution of precision_). Poglavlje također pokazuje kako DOP pomaže pri odluci koje satelite uzeti u rješenje.

== Od pogreške mjerenja do pogreške položaja

Rješenje najmanjih kvadrata $delta hat(bold(x)) = (bold(G)^T bold(G))^(-1) bold(G)^T bold(y)$ je linearna funkcija mjerenja. Ako su pogreške mjerenja neovisne, nepristrane i jednake varijance $sigma^2$, kovarijanca rješenja je

$ "cov"(delta hat(bold(x))) = sigma^2 (bold(G)^T bold(G))^(-1) = sigma^2 bold(Q) . $ <eq:cov>

Matrica $bold(Q)$ ovisi *samo o geometriji*. Ako je $bold(G)$ izražena u lokalnom sustavu istok–sjever–gore (pogl. @pog:koordinate), dijagonala $bold(Q)$ redom daje varijance po istoku, sjeveru, visini i satu. Iz njih se definiraju faktori razrjeđenja preciznosti:

$ "GDOP" = sqrt(Q_(E E) + Q_(N N) + Q_(U U) + Q_(t t)) , quad
  "PDOP" = sqrt(Q_(E E) + Q_(N N) + Q_(U U)) , $
$ "HDOP" = sqrt(Q_(E E) + Q_(N N)) , quad "VDOP" = sqrt(Q_(U U)) , quad "TDOP" = sqrt(Q_(t t)) . $ <eq:dop>

Pravilo koje treba zapamtiti je

$ sigma_"položaj" approx "DOP" times sigma_"UERE" , $ <eq:dopuere>

gdje je $sigma_"UERE"$ (_user equivalent range error_) ukupna standardna devijacija pogreške pseudoudaljenosti iz poglavlja @pog:pogreske. @fig:hdop provjerava to pravilo na simulatoru: snapshot rješenja s namjerno slučajnim podskupovima satelita daju HDOP od #br(B.hdop_raspon.at(0), d: 1) do više od #br(B.hdop_raspon.at(1), d: 0), a horizontalna pogreška raste proporcionalno. Iz omjera se dobiva $sigma_"UERE" approx$ #br(B.uere_iz_hdop) m, u skladu s proračunom pogrešaka (@tab:budget).

#figure(
  image("../slike/07-pogreska-hdop.svg", width: 90%),
  caption: [Horizontalna pogreška snapshot LS rješenja u ovisnosti o HDOP-u (Zagreb, samo GPS, #B.n_epoha_hdop epoha sa slučajnim podskupom od četiri do svih vidljivih satelita, log-mjerilo). Iscrtkani pravac je @eq:dopuere. Prikazane su epohe s HDOP ≤ 20, a izostavljenih #br(B.udio_hdop_iznad_20)% imaju gotovo singularnu geometriju.],
) <fig:hdop>

== Geometrijska intuicija

Svaki redak matrice $bold(G)$ je jedinični vektor prema satelitu, uz jedinicu za sat. Kad su sateliti raspršeni po nebu, retci su „”, $bold(G)^T bold(G)$ je dobro uvjetovana i $bold(Q)$ je mala. Kad su zbijeni u malom dijelu neba, retci su gotovo jednaki, $bold(G)^T bold(G)$ je gotovo singularna i DOP eksplodira. Za četiri satelita GDOP je obrnuto proporcionalan volumenu tetraedra koji razapinju vrhovi jediničnih vektora.

Dva primjera s četiri satelita:

- jedan u zenitu i tri na horizontu, razmaknuta po 120°: GDOP = #br(B.primjer_dobra.G, d: 2), HDOP = #br(B.primjer_dobra.H, d: 2), VDOP = #br(B.primjer_dobra.V, d: 2);
- jedan u zenitu i tri na elevaciji 80°: GDOP = #br(B.primjer_losa.G, d: 0), HDOP = #br(B.primjer_losa.H, d: 1), VDOP = #br(B.primjer_losa.V, d: 0).

U drugom slučaju pogreška mjerenja od 4 m postala bi pogreška visine od preko 300 m.

== Zašto je visina lošija od položaja u ravnini

Gotovo uvijek je VDOP veći od HDOP-a. Razlog je da su svi sateliti *iznad* prijemnika. U horizontalnoj ravnini sateliti su raspoređeni sa svih strana, pa se pogreške u suprotnim smjerovima djelomično poništavaju. U visini su svi s iste strane. Zato se pogreška visine i pogreška sata teško razdvajaju. Pomak sata skraćuje sve pseudoudaljenosti jednako, a pomak prijemnika prema gore skraćuje ih gotovo jednako: za satelit u zenitu puni iznos, za satelit na elevaciji $epsilon$ tek $sin epsilon$ puta toliko. Razliku između ta dva učinka vide samo niski sateliti, pa su oni ključni za visinu.

@fig:dopdan prikazuje DOP-ove kroz dan u Zagrebu za idealizirani GPS. Medijan HDOP-a je #br(B.dop_Zagreb.H.med, d: 2), a VDOP-a #br(B.dop_Zagreb.V.med, d: 2). Skokovi se poklapaju s trenucima kad satelit izađe ili zađe.

#figure(
  image("../slike/07-dop-dan.svg", width: 96%),
  caption: [DOP-ovi kroz 24 sata u Zagrebu (idealizirani GPS, svi sateliti iznad 5°) i broj vidljivih satelita (sivo, desna os).],
) <fig:dopdan>

Geometrija ima i smjer unutar ravnine. Zbog rupe na sjeveru (pogl. @pog:orbite) u Zagrebu je standardna devijacija po sjeveru u medijanu #br(B.dop_Zagreb.N_E_omjer, d: 2) puta veća nego po istoku. U Quitu je omjer #br(B.dop_Quito.N_E_omjer, d: 2).

== Koje satelite uzeti?

Dodavanje satelita nikad ne povećava DOP: $bold(G)^T bold(G)$ dobiva još jedan pozitivno semidefinitan pribrojnik. Ali novi satelit može biti loš (nizak, slab, s multipathom), pa ga treba otežati (pogl. @pog:ls) ili izostaviti. Prijemnici zato biraju podskup. Neki to rade zbog ograničenog broja kanala, a neki zbog računske cijene.

Simulator bira pohlepno (#kod("measurement.select_best_satellites")): među praćenim satelitima redom dodaje onaj koji najviše smanji GDOP, do najviše deset. Računa *iz procijenjenog položaja*, jer pravi prijemnik ne zna stvarni. Koliko je ta granica dobra pokazuje studija u sandboxu (@fig:studije, lijevo): sa sva četiri sustava horizontalna pogreška p95 pada s #br(nadji(MS, 4).h_err_p95.mean) m uz četiri satelita na #br(nadji(MS, 10).h_err_p95.mean) m uz deset i #br(nadji(MS, 20).h_err_p95.mean) m uz dvadeset.

#napomena(naslov: "Pošteno o granici od deset satelita")[
  Granica od deset satelita uvedena je u ranijoj verziji simulatora, kada sva mjerenja još nisu bila otežana po C/N0. Tada su dodatni niski sateliti donosili više šuma nego koristi i greška je iznad desetak satelita rasla. S današnjim težinama dodatni sateliti pomažu do kraja testiranog raspona. Ovo je primjer kako zaključak vrijedi samo uz model za koji je izveden, i zašto ga treba ponovno provjeriti kad se model promijeni.
]

Drugi način odabira je *elevacijska maska*. Viša maska izbacuje najšumovitija mjerenja, ali i najkorisnije satelite za visinu. Za samo GPS studija (@fig:studije, desno) pokazuje da je prijelaz s 5° na 10° gotovo bez učinka, a od 15° naviše geometrija se brzo kvari. Medijan GDOP-a raste s #br(nadji(MK, 5).gdop_median.mean, d: 1) na #br(nadji(MK, 25).gdop_median.mean, d: 1) uz masku 25°, vertikalna pogreška p95 raste s #br(nadji(MK, 5).v_err_p95.mean, d: 1) m na #br(nadji(MK, 25).v_err_p95.mean, d: 1) m, a uz masku 30° fix postoji samo u #br(nadji(MK, 30).availability.mean * 100, d: 0)% epoha.

#figure(
  image("../slike/07-studije.svg", width: 100%),
  caption: [Sandbox studije (Zagreb, EKF, srednja vrijednost preko sjemena uz 95 % interval pouzdanosti). Lijevo: četiri sustava, najveći broj satelita u rješenju (8 sjemena × 120 s). Desno: samo GPS, elevacijska maska (10 sjemena × 180 s). Specifikacije su u #kod("docs/udzbenik/studije/").],
) <fig:studije>

#kljucno[
  - $sigma_"položaj" approx "DOP" times sigma_"UERE"$: točnost je umnožak kvalitete mjerenja i kvalitete geometrije.
  - Visina je gotovo uvijek lošija od položaja u ravnini, jer su svi sateliti iznad nas.
  - Više satelita nikad ne pogoršava DOP, ali može pogoršati točnost ako se loša mjerenja ne otežaju.
]

#vjezba(vrsta: "racunska", naslov: "DOP četiri satelita", rjesenje: [
  Za jedan satelit u zenitu i tri na horizontu (azimuti 0°, 120°, 240°) retci su $(0, 0, -1, 1)$ i $(-sin A_k, -cos A_k, 0, 1)$. Zbog simetrije je $bold(G)^T bold(G)$ dijagonalna u $(E, N)$, a $(U, t)$ blok je $mat(1, -1; -1, 4)$. Inverzija daje GDOP = #br(B.primjer_dobra.G, d: 2), HDOP = #br(B.primjer_dobra.H, d: 2), VDOP = #br(B.primjer_dobra.V, d: 2) i TDOP = #br(B.primjer_dobra.T, d: 2). Kad se tri satelita podignu na 5°, GDOP naraste tek na #br(B.primjer_dobra5.G, d: 2). Za tri satelita na 80° GDOP je #br(B.primjer_losa.G, d: 0): stupci za visinu i sat postaju gotovo jednaki.
])[
  Napiši matricu $bold(G)$ u ENU za četiri satelita: jedan u zenitu i tri na horizontu s azimutima 0°, 120° i 240°. Izračunaj $bold(Q) = (bold(G)^T bold(G))^(-1)$ i sve DOP-ove iz @eq:dop. Ponovi kad su tri satelita na elevaciji 80°. Objasni zašto je u drugom slučaju VDOP toliko velik, a HDOP nije.
]

#vjezba(vrsta: "vodjena", naslov: "DOP u pogledu iznutra", rjesenje: [
  Kartica prikazuje $bold(G)$ u ENU, $bold(Q) = (bold(G)^T bold(G))^(-1)$ i DOP-ove. GDOP se poklapa s onim u telemetriji. VDOP je veći od HDOP-a, a dijagonalni element za sjever obično je veći od onog za istok (rupa na sjeveru). Isključivanje satelita s najnižom elevacijom poveća VDOP osjetno više nego HDOP. Isključivanje satelita blizu zenita slabije mijenja DOP-ove.
])[
  Otvori #ui("Pogled iznutra (matematika epohe)…") i karticu #ui("2. Geometrija"). Pronađi $bold(Q)$ i DOP-ove i usporedi GDOP s telemetrijom. Koji je dijagonalni element najveći? Zatim isključi satelit s najnižom elevacijom (kružić u tablici #ui("Sateliti u vidokrugu")), osvježi pogled i usporedi. Ponovi sa satelitom najbližim zenitu.
]

#vjezba(vrsta: "vodjena", naslov: "Urbani kanjon", rjesenje: [
  Bez satelita ispod 30° ostaje ih obično tri do pet, svi visoko na nebu. GDOP skoči na 5–15 ili više, a pogreška, osobito po visini, naraste nekoliko puta, kao u desnom dijelu @fig:studije. Uključivanjem ostalih sustava broj satelita se vraća na desetak i GDOP pada ispod 2. Upravo je to glavna praktična korist multi-GNSS-a u gradovima (pogl. @pog:multignss).
])[
  Simuliraj prijemnik u uskoj ulici: isključi u tablici sve GPS satelite ispod 30° elevacije. Što se događa s GDOP-om i pogreškom? Zatim u panelu #ui("Sustavi") uključi Galileo, GLONASS i BeiDou te opet isključi satelite ispod 30°. Usporedi.
]

#vjezba(vrsta: "istrazivacka", naslov: "Koliko satelita?", rjesenje: [
  Studija iz #kod("docs/udzbenik/studije/max_sats.json") za četiri sustava daje sljedeće srednje vrijednosti horizontalne pogreške p95 (uz 95 % CI): #MS.map(p => [#p.x: #br(p.h_err_p95.mean, d: 1) m]).join(", "). GDOP pada od #br(nadji(MS, 4).gdop_median.mean, d: 1) (četiri satelita) do #br(nadji(MS, 20).gdop_median.mean, d: 2). Najveći skok je između pet i osam satelita, a iznad deset dobitak je manji, ali i dalje stvaran (intervali pouzdanosti se ne preklapaju između 10 i 20). Usporedbu s WLS-om i samo GPS-om dobiješ istom studijom uz izmijenjen spec. Rezultat ovisi o tvom pokretanju, a očekuje se da WLS bude lošiji od EKF-a (pogl. @pog:kalman).
])[
  Pokreni studiju #kod("python sandbox.py run docs/udzbenik/studije/max_sats.json --workers 4"). Za koji broj satelita prestaje vrijediti „”? Usporedi trend horizontalne pogreške i GDOP-a. Ponovi s estimatorom #kod("wls") i s #kod("\"systems\": [\"GPS\"]"). Što se mijenja?
]
