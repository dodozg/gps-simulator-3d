#import "../predlozak.typ": *
#let B = json("../skripte/brojke_02.json")

= Koordinatni sustavi i vrijeme <pog:koordinate>


#cilj(
  [pretvarati koordinate između ECEF-a, WGS-84 i lokalnog sustava istok–sjever–gore],
  [računati azimut i elevaciju satelita],
  [zašto je Sagnacova korekcija nužna i kako se njezino izostavljanje vidi u položaju],
  [kako relativnost utječe na satove satelita],
)

Pseudoudaljenost povezuje dvije točke u prostoru i dva trenutka u vremenu. Da bi jednadžba pseudoudaljenosti (pogl. @pog:ls) imala smisla, sve četiri veličine moraju biti izražene u istom koordinatnom sustavu i istoj vremenskoj skali. Ovo poglavlje uvodi sustave koje GNSS koristi i pokazuje koliko skupo staje kad se jedan mali član izostavi.

== Inercijalni i Zemljom vezani sustav

Sateliti se gibaju po Newtonovim zakonima, koji vrijede u *inercijalnom* sustavu (ECI, _Earth-Centred Inertial_): ishodište u središtu mase Zemlje, a osi usmjerene prema dalekim zvijezdama. Prijemnik pak stoji na Zemlji koja se okreće kutnom brzinom

$ omega_E = 7","292 space 115 space 9 dot 10^(-5) "rad/s" , $

pa je za njega prirodan sustav *vezan uz Zemlju* (ECEF, _Earth-Centred Earth-Fixed_): os $z$ prema sjevernom polu, os $x$ kroz presjek ekvatora i nultog meridijana, os $y$ ih nadopunjuje do desnog sustava. Položaj točke na Zemlji u ECEF-u je (bez tektonike) konstantan.

Prijelaz iz ECI u ECEF je rotacija oko osi $z$ za kut koji Zemlja prijeđe:

$ bold(r)_"ECEF" = bold(R)_z (theta(t)) space bold(r)_"ECI", quad
  bold(R)_z (theta) = mat(cos theta, sin theta, 0; -sin theta, cos theta, 0; 0, 0, 1) . $ <eq:rot>

U idealiziranom modelu simulatora (#kod("physics_engine.calculate_orbital_position")) je $theta = omega_E t$, tj. oba sustava se poklapaju u $t = 0$. Za prave orbite (pogl. @pog:orbite) $theta$ je Greenwichko srednje zvjezdano vrijeme (GMST) u stvarnom trenutku UTC, pa se globus okreće točno kao prava Zemlja.

Navigacijska poruka daje položaj satelita odmah u ECEF-u, pa prijemnik rješava položaj u ECEF-u. Kvaka je u tome što su položaj satelita u trenutku *odašiljanja* i položaj prijemnika u trenutku *prijama* izraženi u dva ECEF sustava koji su se međusobno zakrenuli. O tome više u odjeljku o Sagnacovom efektu.

== Elipsoid WGS-84 i geodetske koordinate

Zemlja nije kugla nego spljošteni rotacijski elipsoid. GPS koristi elipsoid *WGS-84*:

$ a = 6 space 378 space 137 "m" , quad f = 1 \/ 298","257 space 223 space 563 , quad e^2 = f(2 - f) . $

Geodetska širina $phi$, dužina $lambda$ i visina $h$ iznad elipsoida pretvaraju se u ECEF izravno:

$ x = (N + h) cos phi cos lambda, quad y = (N + h) cos phi sin lambda, quad z = (N (1 - e^2) + h) sin phi , $ <eq:lla>

uz polumjer zakrivljenosti u prvom vertikalu $N = a \/ sqrt(1 - e^2 sin^2 phi)$. Obrnuta pretvorba nema zatvoreni oblik. Simulator (#kod("utils.ecef_to_lla")) koristi Bowringovu metodu, koja konvergira na razinu ispod milimetra u nekoliko koraka.

*Geodetska* širina (kut normale na elipsoid prema ekvatoru) nije isto što i *geocentrična* širina (kut spojnice sa središtem Zemlje). Za Zagreb (45,815°) geocentrična širina je #br(B.geocentricna_sirina_deg, d: 3)°, dakle manja za gotovo 0,2°. To je na tlu oko 21 km. Karte i GNSS prijemnici uvijek prikazuju geodetsku širinu.

#napomena(naslov: "Gdje simulator pojednostavljuje")[
  Idealizirane orbite računaju se na sfernoj Zemlji polumjera 6371 km, a modeli ionosfere i troposfere elevaciju računaju iz geocentričnog „”. Položaji prijemnika, pretvorbe koordinata i sve pogreške u lokalnom sustavu (ENU) koriste WGS-84. Razlika u elevaciji je ispod 0,2° i ne utječe na zaključke ove knjige.
]

== Lokalni sustav istok–sjever–gore

Pogreška od „” ne govori mnogo. Zanima nas je li prijemnik pogriješio vodoravno ili po visini, i u kojem smjeru. Zato se razlike položaja izražavaju u *lokalnom* sustavu ENU (_East–North–Up_) s ishodištem u prijemniku. Jedinični vektori u točki $(phi, lambda)$ su

$ bold(e) = vec(-sin lambda, cos lambda, 0), quad
  bold(n) = vec(-sin phi cos lambda, -sin phi sin lambda, cos phi), quad
  bold(u) = vec(cos phi cos lambda, cos phi sin lambda, sin phi) , $ <eq:enu>

a razlika $Delta bold(r)$ u ECEF-u prelazi u ENU skalarnim produktima: $Delta E = bold(e) dot Delta bold(r)$, $Delta N = bold(n) dot Delta bold(r)$, $Delta U = bold(u) dot Delta bold(r)$.

Smjer prema satelitu u ENU-u opisuju dva kuta: *azimut* $A$ (od sjevera prema istoku) i *elevacija* $epsilon$ (iznad horizonta):

$ A = "atan2"(Delta E, Delta N), quad epsilon = arcsin((Delta U) / norm(Delta bold(r))) . $ <eq:azel>

Ove kutove prikazuje tablica #ui("Sateliti u vidokrugu") (stupci #ui("Elev") i #ui("Azimut")), a #ui("Skyplot (uživo)") ih crta kao polarni dijagram: sredina je zenit, rub horizont, a sjever je gore.

== Vremenske skale

GNSS računa vrijeme u vlastitoj, neprekinutoj atomskoj skali. *GPS vrijeme* počelo je 6. siječnja 1980. i izražava se kao broj tjedna i sekunda unutar tjedna (TOW, _time of week_). Za razliku od UTC-a, GPS vrijeme nema prijestupnih sekundi, pa je danas ispred UTC-a za 18 s. Galileo, GLONASS i BeiDou imaju vlastite skale. Razlike među njima prijemnik vidi kao konstantni pomak pseudoudaljenosti po sustavu (ISB, pogl. @pog:multignss).

Simulator ima vlastito simulacijsko vrijeme $t$ (sekunde od početka sesije). S idealiziranim orbitama doba dana za ionosferu zadaje klizač #ui("Doba dana (ionosfera)"). S pravim orbitama $t$ je vezan za stvarni UTC odabrane epohe, a doba dana je GPS vrijeme te epohe, pa je klizač onemogućen.

== Sagnacov efekt

Signal putuje oko 70–85 ms. Za to vrijeme Zemlja se zakrene za $omega_E tau approx 5 dot 10^(-6)$ rad. Prijemnik u Zagrebu giba se s njom brzinom od #br(B.v_rot_mps, d: 0) m/s prema istoku, pa se za 75 ms pomakne za #br(B.pomak_75ms_m) m. Ako se položaj satelita u trenutku odašiljanja izrazi u ECEF-u trenutka odašiljanja, a prijemnik u ECEF-u trenutka prijama, geometrijska udaljenost nije ona koju je signal stvarno prešao. Popravak prvog reda je

$ Delta rho_"Sagnac" = omega_E / c (x_s y - y_s x) , $ <eq:sagnac>

gdje su $(x_s, y_s)$ koordinate satelita, a $(x, y)$ prijemnika. Korekcija ovisi o tome je li satelit istočno ili zapadno od prijemnika (@fig:sagnac). Za satelite vidljive iz Zagreba kreće se od #br(B.sagnac_min_m) m do #br(B.sagnac_max_m) m. To nije zanemarivo: nekoliko puta je veće od svih ostalih pogrešaka mjerenja zajedno.

#figure(
  image("../slike/02-sagnac-azimut.svg", width: 90%),
  caption: [Sagnacova korekcija za satelite vidljive iz Zagreba kroz 12 sati u ovisnosti o azimutu. Sateliti na istoku imaju pozitivnu, a na zapadu negativnu korekciju. Ovisnost o elevaciji je slabija.],
) <fig:sagnac>

=== Studija slučaja: 25 metara laži skrivenih u šumu

U ranoj verziji simulatora prijemnik je Sagnacovu korekciju uredno *dodavao u model*, ali je mjerni model *nije unosio u mjerenje*. Dok je šum mjerenja bio reda 50 m, ništa se nije primijetilo. Kad je šum smanjen, pogreška je prestala padati i zastala na oko 25 m.

Dijagnoza nije došla iz iznosa pogreške, nego iz njezinog *smjera*. Rastav pogreške u ENU prema @eq:enu i usrednjavanje kroz vrijeme pokazali su stalan pomak od 25 m prema istoku, uz nulu na sjeveru i visini. Šum i multipath nemaju smjer, ali Sagnac ima (@fig:sagnac). @fig:bezsagnaca reproducira istu grešku obrnuto: mjerenja su ispravna, a iz modela prijemnika uklonjen je član @eq:sagnac. Srednji pomak je (#br(B.bez_sagnaca_sred_enu_m.at(0), d: 1); #br(B.bez_sagnaca_sred_enu_m.at(1), d: 1); #br(B.bez_sagnaca_sred_enu_m.at(2), d: 1)) m u smjeru istok, sjever, gore. S ispravnim modelom sve tri komponente su unutar pola metra od nule.

#figure(
  image("../slike/02-bez-sagnaca.svg", width: 70%),
  caption: [Horizontalna pogreška kroz 600 epoha uz iste pseudoudaljenosti, s ispravnim modelom i s modelom bez Sagnacove korekcije (Zagreb, samo GPS). Križić označava srednju vrijednost oblaka.],
) <fig:bezsagnaca>

Simulator od tada ima *test bez šuma* (#kod("tests/test_consistency.py")): svi slučajni izvori se isključe, a pogreška položaja mora pasti ispod centimetra (postiže se oko 10 µm). Svaka nedosljednost između onoga što se ubrizgava u mjerenje i onoga što prijemnik korigira podigla bi tu pogrešku s mikrometara na metre.

#kljucno[
  - Pogrešku položaja uvijek rastavi u ENU. *Smjer* pogreške otkriva uzrok, a iznos rijetko.
  - Pristranost koja ne nestaje usrednjavanjem nije šum. Ona je nedosljednost modela.
]

== Relativnost

Satovi na satelitima idu drukčije od satova na Zemlji, zbog dva učinka. Zbog brzine (specijalna relativnost) kasne oko 7 µs na dan, a zbog slabijeg gravitacijskog potencijala (opća relativnost) žure oko 45 µs na dan. Neto učinak je da žure približno 38 µs na dan. Simulator koristi stalnu stopu od #br(B.rel_drift_s_po_s * 1e10, d: 2)$dot 10^(-10)$, što je #br(B.rel_us_po_danu) µs na dan, ili #br(B.rel_km_po_danu) km pogreške udaljenosti na dan. Stvarni GPS taj dio uklanja tako da satove na satelitima namjerno malo uspori prije lansiranja.

Drugi, periodički dio potječe od ekscentriciteta orbite:

$ Delta t_"rel" = -(2 sqrt(mu a)) / c^2 e sin E , $ <eq:rel>

gdje je $E$ ekscentrična anomalija (pogl. @pog:orbite). Za ekscentricitet idealizirane GPS orbite u simulatoru ($e = #B.ekscentricitet_walker$) amplituda je #br(B.rel_ekscentr_amp_ns) ns, tj. #br(B.rel_ekscentr_amp_m) m. U simulatoru se oba učinka uključuju u sat satelita i jednako tako korigiraju preko navigacijske poruke, pa za ispravan satelit nestaju.

#vjezba(vrsta: "racunska", naslov: "Zagreb u ECEF-u", rjesenje: [
  Uz $phi = 45","815°$, $lambda = 15","982°$, $h = 120$ m: $N = #br(B.zagreb_N_m)$ m, pa je $bold(r) = (#br(B.zagreb_ecef_m.at(0), d: 1); #br(B.zagreb_ecef_m.at(1), d: 1); #br(B.zagreb_ecef_m.at(2), d: 1))$ m. Udaljenost od središta je $norm(bold(r)) approx$ #br(B.zagreb_r_km) km, manje od ekvatorskog polumjera jer je Zemlja spljoštena. Geocentrična širina je $arctan(z \/ sqrt(x^2 + y^2)) = #br(B.geocentricna_sirina_deg, d: 4)°$.
])[
  Prema @eq:lla izračunaj ECEF koordinate Zagreba (45,815° N, 15,982° E, 120 m). Kolika je udaljenost od središta Zemlje? Izračunaj geocentričnu širinu i usporedi je s geodetskom.
]

#vjezba(vrsta: "racunska", naslov: "Azimut i elevacija", rjesenje: [
  Razlika satelit − prijemnik u ENU je približno (#br(B.vjezba_enu_km.at(0)); #br(B.vjezba_enu_km.at(1)); #br(B.vjezba_enu_km.at(2))) km, pa je azimut #br(B.vjezba_az_deg, d: 1)° (jugoistok), a elevacija #br(B.vjezba_el_deg, d: 1)°. Satelit je visoko na nebu.
])[
  Uzmi prvi satelit (#raw(B.vjezba_sat)) iz datoteke #kod("podaci/epoha_zagreb.csv") i položaj Zagreba iz prethodne vježbe. Prema @eq:enu i @eq:azel izračunaj njegov azimut i elevaciju. Na kojoj je strani neba?
]

#vjezba(vrsta: "vodjena", naslov: "Skyplot i tablica", rjesenje: [
  Svaki redak tablice odgovara točki na skyplotu: elevacija 90° je središte, 0° rub, a azimut se čita u smjeru kazaljke na satu od sjevera. Sateliti se po skyplotu pomiču polako, nekoliko stupnjeva u minuti, jer im ophodno vrijeme iznosi približno 12 sati. Satelit koji izlazi pojavljuje se na rubu, a nestaje kad padne ispod maske od 5°.
])[
  Pokreni simulaciju u svom gradu i otvori #ui("Skyplot (uživo)") u donjem doku. Odaberi satelit iz tablice #ui("Sateliti u vidokrugu") i pronađi ga na skyplotu prema #ui("Elev") i #ui("Azimut"). Postavi klizač #ui("Brzina") na 60× i promatraj dvije minute. Kako se sateliti gibaju? Gdje se pojavljuju novi?
]

#vjezba(vrsta: "racunska", naslov: "Koliki je Sagnac?", rjesenje: [
  Prijemnik na 45° širine giba se zbog rotacije Zemlje brzinom $omega_E R cos phi approx #br(B.v_rot_mps, d: 0)$ m/s prema istoku i za vrijeme leta od oko 75 ms pomakne se #br(B.pomak_75ms_m) m. Korekcija je projekcija tog pomaka na smjer prema satelitu, pa je najveća za satelite nisko na istoku ili zapadu (do oko #br(calc.abs(B.sagnac_min_m), d: 0) m), a gotovo nula za satelite na sjeveru, jugu ili u zenitu (@fig:sagnac). Zato sve pogreške imaju isti smjer: mjerenja prema istočnim satelitima su sustavno preduga, a prema zapadnim prekratka. Ako ih model ne korigira, rješenje se pomakne duž osi istok–zapad, i to uvijek u istu stranu (@fig:bezsagnaca).
])[
  Procijeni red veličine Sagnacove korekcije prema @eq:sagnac za GPS satelit i prijemnik na 45° širine. Kad je korekcija najveća? Objasni zašto njezino izostavljanje pomiče rješenje baš prema istoku.
]

#vjezba(vrsta: "racunska", naslov: "Relativnost u metrima", rjesenje: [
  (a) $38 dot 10^(-6) "s" dot c approx 11","4$ km na dan, odnosno oko 0,13 m svake sekunde. Bez korekcije položaj bi se kvario brzinom od nekoliko kilometara na dan. (b) Uz $a = 26 space 571$ km i $e = 0","015$: $2 sqrt(mu a) \/ c^2 dot e = #br(B.rel_ekscentr_amp_ns)$ ns $approx #br(B.rel_ekscentr_amp_m)$ m. Za stvarne GPS satelite ($e lt.eq 0","02$) to je do oko 14 m, pa se taj član uvijek mora korigirati.
])[
  (a) Koliku pogrešku udaljenosti dnevno stvara neto relativistički pomak od 38 µs/dan ako se ne korigira? (b) Prema @eq:rel izračunaj amplitudu periodičkog člana za $a = 26 space 571$ km i $e = 0","015$.
]
