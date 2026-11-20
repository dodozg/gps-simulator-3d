#import "../predlozak.typ": *
#let B = json("../skripte/brojke_03.json")

= Orbite i konstelacije <pog:orbite>


#cilj(
  [izračunati položaj satelita iz Keplerovih elemenata],
  [kako spljoštenost Zemlje (J2) okreće orbite],
  [kako je složena konstelacija Walker-Delta i po čemu se prave orbite razlikuju],
  [zašto se s naših širina sateliti ne vide na sjeveru],
)

Prijemnik može riješiti položaj samo ako zna gdje su sateliti bili u trenutku odašiljanja. Navigacijska poruka zato nosi parametre orbite, a prijemnik iz njih računa položaj satelita. Ovo poglavlje pokazuje kako se iz šest brojeva dobiva položaj satelita, zašto su GNSS konstelacije složene upravo tako kako jesu i što iz toga slijedi za korisnika na Zemlji.

== Keplerovi elementi

U polju točkaste mase satelit se giba po elipsi u nepomičnoj ravnini. Šest *Keplerovih elemenata* potpuno je opisuju:

- veličina i oblik: velika poluos $a$ i ekscentricitet $e$;
- položaj ravnine: inklinacija $i$ (nagib prema ekvatoru) i rektascenzija uzlaznog čvora $Omega$ (gdje ravnina presijeca ekvator idući prema sjeveru);
- orijentacija elipse u ravnini: argument perigeja $omega$;
- položaj satelita na elipsi u referentnom trenutku: srednja anomalija $M_0$.

Iz trećeg Keplerovog zakona slijedi srednje gibanje i ophodno vrijeme:

$ n = sqrt(mu / a^3) , quad T = (2 pi) / n , quad mu = 3","986 space 004 space 418 dot 10^14 "m"^3"/s"^2 . $ <eq:kepler3>

Za GPS ($a$ = #br(B.GPS.a_km, d: 0) km u simulatoru) to je $T$ = #br(B.GPS.T_min) min, gotovo točno pola zvjezdanog dana (23 h 56 min 4 s). GPS satelit napravi #br(B.GPS.ophoda_po_zv_danu, d: 3) ophoda dnevno, pa se nad istom točkom Zemlje pojavljuje svaki dan oko 4 minute ranije. Cijela konstelacija ponavlja geometriju nad prijemnikom svakih 86 164 s. Zato istraživački sandbox, kad želi slučajnu geometriju, pomiče početak simulacije unutar jednog zvjezdanog dana (pogl. @pog:projekti).

== Od elemenata do položaja

Srednja anomalija raste jednoliko, $M(t) = M_0 + n t$, ali satelit se na elipsi ne giba jednoliko. Veza s *ekscentričnom anomalijom* $E$ je Keplerova jednadžba

$ M = E - e sin E , $ <eq:keplereq>

koja nema zatvoreno rješenje. Za male ekscentricitete Newton-Raphsonova iteracija $E_(k+1) = E_k - (E_k - e sin E_k - M) \/ (1 - e cos E_k)$ iz $E_0 = M$ konvergira u dva do tri koraka. Položaj u ravnini orbite je zatim

$ x' = a (cos E - e), quad y' = a sqrt(1 - e^2) sin E , $ <eq:ravnina>

a u inercijalni sustav ga prevode tri rotacije: $bold(r) = bold(R)_z (Omega) bold(R)_x (i) bold(R)_z (omega) (x', y', 0)^T$. Na kraju rotacija @eq:rot (pogl. @pog:koordinate) daje ECEF. To je točno ono što radi #kod("physics_engine.calculate_orbital_position").

== Spljoštenost Zemlje: perturbacija J2

Zemlja nije točkasta masa. Njezina ekvatorska izbočina (koeficijent $J_2 = 1","082 space 63 dot 10^(-3)$) okreće ravninu orbite i elipsu unutar nje. Prvi red sekularnih promjena je

$ dot(Omega) = -3/2 n J_2 (R_E / a)^2 cos i , quad
  dot(omega) = 3/4 n J_2 (R_E / a)^2 (4 - 5 sin^2 i) . $ <eq:j2>

Za GPS to je $dot(Omega)$ = #br(B.GPS.lan_dot_deg_dan, d: 4)°/dan i $dot(omega)$ = #br(B.GPS.w_dot_deg_dan, d: 4)°/dan. Malo, ali kroz godinu ravnina se zakrene za oko 14°, pa kontrolni segment mora povremeno korigirati orbite. Simulator uključuje oba člana. Emitirane efemeride u pravom GPS-u (pogl. @pog:pravi) imaju još šest harmoničkih korekcijskih članova za kratkoperiodičke učinke.

== Konstelacija Walker-Delta

Za globalno pokrivanje treba rasporediti dvadesetak satelita tako da se iz svake točke uvijek vidi barem četiri, po mogućnosti dobro raspršena. Standardni recept je *Walker-Delta* konstelacija $T\/P\/F$: $T$ satelita u $P$ jednako razmaknutih ravnina iste inklinacije, po $T\/P$ jednako razmaknutih u svakoj ravnini, uz pomak faze između susjednih ravnina od $F dot 360° \/ T$. Idealizirani GPS u simulatoru je $24\/6\/1$ na 55° (#kod("satellite.WalkerDeltaConstellation")), a Galileo, GLONASS i BeiDou su $24\/3\/1$ s nazivnim visinama i inklinacijama iz @tab:sustavi[tablice].

#napomena(naslov: "Bug pronađen pišući ovu knjigu")[
  Prilikom pripreme ovog poglavlja provjeren je razmak satelita unutar jedne ravnine. Umjesto očekivanih 0°/90°/180°/270° sateliti su stajali na 0°, 118°, 128° i 10°, dakle u dva zbijena para (@fig:faze). Uzrok: $M_0$ je zadan u stupnjevima, a u @eq:keplereq zbrajao se kao da je u radijanima. Nakon ispravka medijan pogreške položaja (samo GPS, četiri lokacije) pao je s 6,2 m na 3,9 m, a GDOP s 3,1 na 2,3. Pouka: provjeri ulazne pretpostavke modela jednostavnim, neovisnim mjerenjem. Ovdje je to bio kut između dva vektora.
]

#figure(
  image("../slike/03-walker-faze.svg", width: 66%),
  caption: [Položaj četiri satelita prve ravnine idealiziranog GPS-a u $t = 0$ (argument širine), prije i nakon ispravka jedinice za $M_0$.],
) <fig:faze>

== Prave orbite

Idealizirana konstelacija dobra je za učenje, ali stvarni sateliti nisu tako uredni: ima ih više od nazivnog broja, ravnine nisu jednako popunjene, a BeiDou uz MEO ima i geostacionarne (GEO) i nagnute geosinkrone (IGSO) satelite. Odabirom #ui("Prave (CelesTrak)") simulator koristi javne orbitalne elemente (format OMM, istovrsni starijim TLE-ovima) koje objavljuje CelesTrak. Propagira ih modelom *SGP4*, za duboki svemir SDP4, koji uključuje J2–J4, otpor atmosfere te Sunce i Mjesec. Dobiveni položaj je u sustavu TEME, a u ECEF se prevodi rotacijom za GMST u stvarnom UTC trenutku.

Točnost SGP4 za GNSS satelite je reda kilometra, a nikako metra. Za navigaciju to bi bilo neupotrebljivo, ali u simulatoru je dovoljno, jer prijemnik dobiva emitirani položaj s jednakim modelom pogreške kao kod idealiziranih orbita. Geometrija neba je pritom stvarna.

@fig:tragovi prikazuje tragove nekoliko satelita po Zemlji kroz 24 sata. GPS satelit u tom vremenu dvaput obiđe Zemlju po istom tragu. GLONASS se zbog veće inklinacije penje do 65°. Geostacionarni BeiDou C04 je točka iznad ekvatora, a IGSO satelit crta osmicu.

#figure(
  image("../slike/03-tragovi.svg", width: 96%),
  caption: [Tragovi po Zemlji kroz 24 sata od 20. 11. 2026. 00:00 UTC, prave orbite iz ugrađene snimke elemenata, propagirane SGP4. GEO satelit C04 je praktično nepomičan na oko 160° E.],
) <fig:tragovi>

== Vidljivost: maska elevacije i rupa na sjeveru

Satelit je upotrebljiv kad je iznad horizonta. U praksi se postavlja *maska elevacije* (u simulatoru 5°), jer signali niskih satelita prolaze kroz najviše atmosfere, najslabiji su i najviše ih ometa multipath. Uz to, simulator za svaki satelit baca zraku kroz digitalni model terena (SRTM). Satelit iza planine se ne prati.

Inklinacija od 55° ima posljedicu koju svaki geodet na srednjim širinama poznaje: sateliti nikad ne prolaze iznad 55° geografske širine. Promatrač u Zagrebu ih zato na sjevernom dijelu neba vidi samo nisko, preko pola. Na @fig:skyplot[slici] se iz Zagreba vidi „rupa na sjeveru”. U sektoru ±30° oko sjevera iznad 10° elevacije bilo je samo #br(B.sjever_udio_posto.Zagreb)% položaja GPS satelita kroz dan, a u Quitu na ekvatoru #br(B.sjever_udio_posto.Quito)%. Na Svalbardu je situacija obrnuta: nema satelita u zenitu, ali ih ima uokolo po cijelom horizontu.

#figure(
  image("../slike/03-skyplot-gps.svg", width: 100%),
  caption: [Skyplot svih GPS satelita kroz 24 sata (prave orbite). Središte je zenit, rub horizont, a sjever je gore. U Zagrebu je vidljiva rupa na sjeveru, a na 78° N rupa u zenitu.],
) <fig:skyplot>

Rupa na sjeveru ima izravnu posljedicu za točnost: kad nijedan satelit nije na sjevernom dijelu neba, geometrija u smjeru sjever–jug je slabija nego istok–zapad (pogl. @pog:dop).

#kljucno[
  - Šest Keplerovih elemenata i jednostavna iteracija daju položaj satelita. Prijemnik to radi za svaki satelit u svakoj epohi.
  - Ophodno vrijeme GPS-a je pola zvjezdanog dana, pa se geometrija ponavlja svaki dan oko 4 minute ranije.
  - Inklinacija konstelacije određuje gdje na nebu sateliti *nikad* nisu.
]

#vjezba(vrsta: "racunska", naslov: "Ophodna vremena", rjesenje: [
  Iz @eq:kepler3 uz $R = 6371$ km: GPS $a$ = #br(B.GPS.a_km, d: 0) km, $T$ = #br(B.GPS.T_h, d: 2) h (#br(B.GPS.ophoda_po_zv_danu, d: 2) ophoda po zvjezdanom danu); Galileo #br(B.GAL.T_h, d: 2) h (#br(B.GAL.ophoda_po_zv_danu, d: 2)); GLONASS #br(B.GLO.T_h, d: 2) h (#br(B.GLO.ophoda_po_zv_danu, d: 2)); BeiDou MEO #br(B.BDS.T_h, d: 2) h (#br(B.BDS.ophoda_po_zv_danu, d: 2)). Brzine su redom #br(B.GPS.v_kms, d: 2), #br(B.GAL.v_kms, d: 2), #br(B.GLO.v_kms, d: 2) i #br(B.BDS.v_kms, d: 2) km/s. Samo GPS ima cjelobrojan omjer (2:1). Galileo ponavlja trag tek nakon 10 dana (17 ophoda), a GLONASS nakon 8 dana (17 ophoda). Geostacionarna visina iznad sferne Zemlje je $a - R approx$ #br(B.geo_visina_km_sfera, d: 0) km.
])[
  Za nazivne visine iz @tab:sustavi[tablice] (iznad sfere $R = 6371$ km) izračunaj ophodno vrijeme, broj ophoda po zvjezdanom danu (86 164 s) i brzinu po kružnoj orbiti $v = sqrt(mu \/ a)$ za sva četiri sustava. Koji sustav ima trag po Zemlji koji se ponavlja svaki dan? Na kojoj bi visini satelit bio geostacionaran?
]

#vjezba(vrsta: "racunska", naslov: "Keplerova jednadžba", rjesenje: [
  Iteracija daje $E_0 = 1$, $E_1 = #br(B.kepler_koraci.at(1), d: 10)$, $E_2 = #br(B.kepler_koraci.at(2), d: 10)$, a $E_3$ se poklapa s $E_2$ na 10 decimala. Konvergencija je kvadratna: broj točnih znamenaka se otprilike udvostručuje u svakom koraku. Razlika $E - M approx 0","0127$ rad $approx 0","73°$ pomiče satelit za oko $a(E - M) approx 340$ km duž orbite. Zato se Keplerova jednadžba ne smije preskočiti ni za gotovo kružne orbite.
])[
  Riješi @eq:keplereq Newtonovom metodom za $M = 1$ rad i $e = 0","015$ (ekscentricitet idealiziranog GPS-a u simulatoru). Ispiši $E_k$ za prva tri koraka. Koliko bi kilometara pogriješio položaj satelita da se uzme $E approx M$?
]

#vjezba(vrsta: "vodjena", naslov: "Rupa na sjeveru uživo", rjesenje: [
  U Zagrebu se sateliti na skyplotu kreću kroz južni i središnji dio neba, a na sjevernom rubu se pojavljuju samo nisko. Na ekvatoru (Quito) nebo je pokriveno ravnomjerno. Na Svalbardu sateliti kruže oko zenita, ali ga ne dosežu. Broj satelita u tablici je na sve tri lokacije sličan. Mijenja se njihov *raspored*, a s njim (pogl. @pog:dop) i omjer pogreške po visini i vodoravno.
])[
  Postavi klizač #ui("Brzina") na 300× (stvarno postignuta brzina ispisuje se uz natpis), pokreni simulaciju u Zagrebu i promatraj #ui("Skyplot (uživo)") dok ne prođe barem pola dana simulacije. Ponovi u Quitu (upiši #kod("Quito") u traku #ui("Leti do grada ili koordinata…")) i na Svalbardu (#kod("78.22, 15.65")). Opiši razliku u rasporedu satelita po nebu.
]

#vjezba(vrsta: "vodjena", naslov: "Geostacionarni satelit iz GPS-a", rjesenje: [
  Uz visinu od oko 35 790 km i inklinaciju 0° satelit miruje nad jednom točkom ekvatora: ophodno vrijeme jednako je zvjezdanom danu, a ravnina orbite je ekvatorska. S inklinacijom većom od nule satelit crta osmicu sjever–jug oko te točke (kao IGSO na @fig:tragovi[slici]). Iz Zagreba je takav satelit vidljiv samo ako mu je dužina unutar otprilike ±70° od 16° E, i uvijek nisko na južnom nebu. Satelitu se pritom ne mijenja signal, nego geometrija: stoji na mjestu, pa se njegov doprinos ne mijenja kroz vrijeme.
])[
  S idealiziranim orbitama klikni na redak jednog GPS satelita u tablici da otvoriš editor satelita. Postavi #ui("Visina orbite [km]") na 35790 i #ui("Inklinacija [°]") na 0. Promatraj satelit na globusu (#ui("Fokusiraj kameru")) dok simulacija teče ubrzano. Što se dogodi kad inklinaciju postaviš na 30°? Je li satelit vidljiv iz Zagreba?
]
