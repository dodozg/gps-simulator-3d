#import "../predlozak.typ": *
#let B = json("../skripte/brojke_05.json")

= Pseudoudaljenost i izvori pogrešaka <pog:pogreske>


#cilj(
  [rastaviti pseudoudaljenost na geometriju, satove, atmosferu, multipath i šum],
  [kako iono-free kombinacija uklanja ionosferu i koliko to košta],
  [zašto sporo promjenjive pogreške štete više od bijelog šuma],
  [procijeniti ukupnu pogrešku mjerenja po elevaciji],
)

Pseudoudaljenost iz petlje koda (pogl. @pog:signal) nije samo udaljenost uvećana za sat prijemnika. Signal prolazi kroz ionosferu i troposferu, odbija se od okolnih ploha, a prijemnik računa udaljenost do položaja satelita koji je i sam pogrešan. Ovo poglavlje rastavlja pseudoudaljenost na članove, pokazuje kako se koji uklanja i koliko od svega preostaje, jer upravo taj ostatak određuje točnost položaja.

== Puna jednadžba pseudoudaljenosti

Za satelit $i$ i frekvenciju $f$:

$ rho_i = r_i + c (delta t - delta t^i) + I_i (f) + T_i + M_i + epsilon_i , $ <eq:prpuna>

gdje je $r_i$ geometrijska udaljenost (uz Sagnacovu korekciju, pogl. @pog:koordinate), $delta t$ i $delta t^i$ pogreške sata prijemnika i satelita, $I_i$ ionosfersko, a $T_i$ troposfersko kašnjenje, $M_i$ multipath i $epsilon_i$ šum koda. Prijemnik ne zna ni pravi položaj satelita, nego onaj iz efemerida, pa u modelu računa $hat(r)_i$ s pogreškom duž linije pogleda. U nastavku prolazimo član po član, uvijek s pitanjem: koliko je velik i tko ga uklanja?

== Satovi

*Sat satelita* je atomski i vrlo stabilan, ali nije savršen. Kontrolni segment mjeri njegov pomak i emitira korekciju kao polinom u navigacijskoj poruci. Simulator sat satelita modelira Allanovom varijancom (bijeli šum frekvencije i slučajni hod frekvencije), uz relativističke članove (pogl. @pog:koordinate). Emitirana korekcija sadrži sve to, pa se za ispravan satelit poništi. Ostaje samo ono što korekcija ne zna. Taj ostatak je u stvarnom GPS-u reda veličine metra, a u simulatoru se namjerno ubrizgava kao kvar (editor satelita, #ui("Greška sata (kvar) [m]")).

*Sat prijemnika* nije problem, jer se procjenjuje (pogl. @pog:ls).

== Ionosfera

Ionosfera (oko 50–1000 km) je sloj ioniziranog plina. Za radijski signal je *disperzivna*: kašnjenje grupe (koda) ovisi o frekvenciji,

$ I(f) = (40","3 dot "TEC") / f^2 , $ <eq:iono>

gdje je TEC ukupni sadržaj elektrona duž puta (u elektronima po m²). Jedna jedinica TECU ($10^16$ el/m²) kasni L1 za #br(B.tecu_l1_m, d: 3) m. TEC jako ovisi o dobu dana, Sunčevoj aktivnosti i zemljopisnoj širini.

Jednofrekvencijski prijemnici ionosferu procjenjuju *Klobucharovim modelom*: kosinusom kroz dan s vrhom u 14 h lokalnog vremena i stalnim noćnim pragom, uz faktor nagiba koji raste prema horizontu. Simulator upravo tim modelom ubrizgava ionosferu u mjerenje (#kod("physics_engine.klobuchar_delay")), s koeficijentima kakve emitira GPS pri umjerenoj Sunčevoj aktivnosti (@fig:iono). U Zagrebu zenitno kašnjenje na L1 raste od #br(B.iono_noc_m) m noću do #br(B.iono_vrh_m) m u #B.iono_vrh_h h. Koso, na 5° elevacije oko podneva, iznosi #br(B.iono_l1_5_podne) m.

#figure(
  image("../slike/05-ionosfera.svg", width: 98%),
  caption: [Klobucharov model u simulatoru (Zagreb). Lijevo: zenitno kašnjenje L1 kroz dan. Desno: koso kašnjenje u ovisnosti o elevaciji oko 14 h i noću. L2 kasni $(f_1\/f_2)^2 approx 1","65$ puta više.],
) <fig:iono>

=== Iono-free kombinacija

Disperzija je i slabost i spas. Prijemnik koji mjeri na dvije frekvencije može ionosferu prvog reda *potpuno ukloniti* linearnom kombinacijom

$ rho_"IF" = (f_1^2 rho_1 - f_2^2 rho_2) / (f_1^2 - f_2^2) = #br(B.if_k1, d: 3) rho_1 - #br(B.if_k2, d: 3) rho_2 , $ <eq:if>

jer član $40","3 "TEC"\/f^2$ u brojniku nestaje. Geometrija, satovi i troposfera nisu ovisni o frekvenciji, pa prolaze nepromijenjeni (koeficijenti se zbrajaju u 1). Simulator koristi upravo tu kombinaciju: ostatak ionosfere nakon nje je ispod $10^(-14)$ m. Cijena je šum. Ako su šumovi na L1 i L2 neovisni, iono-free kombinacija ih pojača $sqrt(2","546^2 + 1","546^2) approx 3$ puta (@fig:sumkoda). Multipath je na obje frekvencije posljedica iste geometrije odraza, pa je jako koreliran i kroz kombinaciju prolazi gotovo nepojačan. Simulator ga zato modelira zajedničkim za L1 i L2.

#napomena(naslov: "Zato klizač za doba dana ne mijenja pogrešku")[
  Budući da prijemnik u simulatoru koristi iono-free kombinaciju, pomicanje klizača #ui("Doba dana (ionosfera)") gotovo ne utječe na točnost položaja, iako se kašnjenje na L1 pritom mijenja za više metara. Jednofrekvencijski prijemnik (npr. u većini telefona) bi oko podneva bio znatno lošiji.
]

== Troposfera

Donji, neutralni dio atmosfere (do oko 15 km) usporava signal nezavisno o frekvenciji, pa ga iono-free kombinacija *ne uklanja*. Zenitno kašnjenje je oko 2,3 m od suhog plina i 0,1–0,3 m od vodene pare, a prema horizontu raste otprilike s $1\/sin "el"$. Simulator koristi jednostavan model sa zenitnim kašnjenjem od 2,4 m: na 10° to je #br(B.tropo_10) m, a na 5° #br(B.tropo_5) m. Prijemnik isto kašnjenje računa iz *procijenjenog* položaja i oduzima ga. Ostatak dolazi samo od razlike između stvarnog i procijenjenog položaja, pa je zanemariv.

U stvarnosti je model troposfere izvor pogreške od nekoliko centimetara do decimetara, najviše zbog vlažnog dijela, koji se ne može dobro predvidjeti. Precizne metode ga zato procjenjuju kao dodatnu nepoznanicu.

== Multipath

Signal ne stiže samo izravno. Odraz od tla, zgrade ili vode stiže zakašnjeli i slabiji, a korelator vidi zbroj obaju. Kodni multipath *produljuje* mjerenje, jer odraz uvijek kasni. Zato je u prosjeku pozitivan i ne nestaje usrednjavanjem. Simulator ga modelira dvozračnim modelom s dodatnim putem od 1–12 m i prigušenjem koje odgovara ostatku nakon tehnika ublažavanja u prijemniku, a pojačava ga prema horizontu. Odraz se pritom za svaku epohu bira nanovo (pojednostavljenje: stvarni multipath se mijenja sporo, kako se mijenja geometrija odraza).

== Efemeride

Položaj satelita iz navigacijske poruke je prognoza kontrolnog segmenta s pogreškom reda metra. Bitno je *kako se ta pogreška mijenja u vremenu*: emitirane efemeride vrijede oko dva sata, pa je pogreška za pojedini satelit gotovo stalna i polako luta. Simulator je modelira Gauss-Markovljevim procesom sa standardnom devijacijom 1,5 m po osi i korelacijskim vremenom od 30 minuta (@fig:eph). Za prijemnik je važna samo projekcija na liniju pogleda. U simulaciji iz Zagreba njezina standardna devijacija bila je #br(B.eph_los_std, d: 2) m.

#figure(
  image("../slike/05-efemeride.svg", width: 90%),
  caption: [Pogreška emitiranog položaja satelita projicirana na liniju pogleda za četiri satelita kroz četiri sata simulacije. Pogreška se mijenja sporo, pa je Kalmanov filtar ne može usrednjiti kao bijeli šum.],
) <fig:eph>

Za filtar je to važna razlika. Bijeli šum se usrednjavanjem kroz epohe smanjuje, a sporo promjenjiva pristranost ne. Zato je točnost simulatora nakon uvođenja ovog, realnijeg modela blago *pala*.

== Proračun pogrešaka

Što preostane nakon svih korekcija? @fig:ostatak prikazuje razliku između iono-free pseudoudaljenosti s primijenjenim korekcijama i prave udaljenosti uvećane za sat prijemnika i Sagnac, za sve satelite kroz četiri sata. Taj ostatak čine šum koda pojačan iono-free kombinacijom, multipath i ostatak troposfere. Pogreška efemerida dolazi naknadno, kroz model.

#figure(
  image("../slike/05-ostatak.svg", width: 94%),
  caption: [Ostatak pogreške pseudoudaljenosti nakon korekcija u ovisnosti o elevaciji (Zagreb, samo GPS, četiri sata). Crveno: izmjerena standardna devijacija u razredima od 5°. Iscrtkano: $sigma$ koju prijemnik pretpostavlja prema @eq:sigma.],
) <fig:ostatak>

#figure(
  table(
    columns: 4,
    align: (left, right, right, right),
    [Elevacija], [izmjerena σ], [σ modela], [srednja vrijednost],
    [5–15°], [#br(B.ost_5_15.std, d: 2) m], [#br(B.ost_5_15.model, d: 2) m], [#br(B.ost_5_15.sred, d: 2) m],
    [15–30°], [#br(B.ost_15_30.std, d: 2) m], [#br(B.ost_15_30.model, d: 2) m], [#br(B.ost_15_30.sred, d: 2) m],
    [30–60°], [#br(B.ost_30_60.std, d: 2) m], [#br(B.ost_30_60.model, d: 2) m], [#br(B.ost_30_60.sred, d: 2) m],
    [60–90°], [#br(B.ost_60_90.std, d: 2) m], [#br(B.ost_60_90.model, d: 2) m], [#br(B.ost_60_90.sred, d: 2) m],
  ),
  caption: [Ostatak pogreške pseudoudaljenosti po elevaciji. Model prijemnika blago precjenjuje šum pri horizontu (oprezno), a srednja vrijednost je malo pozitivna zbog multipatha.],
) <tab:budget>

Dva su zaključka važna za ostatak knjige. Prvo, model šuma kojim prijemnik otežava mjerenja dobro odgovara stvarnom ostatku, što je preduvjet za ispravan Kalmanov filtar (pogl. @pog:kalman) i statistički test integriteta (pogl. @pog:raim). Drugo, pogreška mjerenja od nekoliko metara po satelitu još nije pogreška položaja. Koliko se ona pojača ovisi o geometriji, a to je tema poglavlja @pog:dop.

#kljucno[
  - Iono-free kombinacija uklanja ionosferu, ali utrostručuje šum koda. Troposferu ne uklanja.
  - Pogreške koje se sporo mijenjaju (efemeride, multipath) štete više nego jednako velik bijeli šum, jer ih filtar ne može usrednjiti.
  - Model šuma prijemnika mora odgovarati stvarnosti. Pogled iznutra omogućuje to provjeriti satelit po satelit.
]

#vjezba(vrsta: "racunska", naslov: "Iono-free kombinacija", rjesenje: [
  Uvrštavanjem $rho_k = r + I_1 (f_1\/f_k)^2$: $(f_1^2 (r + I_1) - f_2^2 (r + I_1 f_1^2\/f_2^2)) \/ (f_1^2 - f_2^2) = r (f_1^2 - f_2^2)\/(f_1^2 - f_2^2) + (f_1^2 I_1 - f_1^2 I_1)\/(f_1^2 - f_2^2) = r$. Koeficijenti su $k_1 = #br(B.if_k1, d: 3)$ i $k_2 = #br(B.if_k2, d: 3)$ ($k_1 - k_2 = 1$). Za neovisne šumove jednake $sigma$: $sigma_"IF" = sqrt(k_1^2 + k_2^2) sigma approx 2","98 sigma$. Za potpuno korelirani multipath $M$ na obje frekvencije: $k_1 M - k_2 M = M$, dakle bez pojačanja.
])[
  Pokaži da @eq:if uklanja član $I(f) = A\/f^2$. Izračunaj koeficijente uz $rho_1$ i $rho_2$ i faktor pojačanja šuma ako su šumovi na L1 i L2 neovisni i jednake standardne devijacije. Što se događa s multipathom koji je na obje frekvencije jednak?
]

#vjezba(vrsta: "racunska", naslov: "TEC i kašnjenje", rjesenje: [
  1 TECU daje $40","3 dot 10^16 \/ (1","575 space 42 dot 10^9)^2 approx #br(B.tecu_l1_m, d: 3)$ m na L1 i $(f_1\/f_2)^2 = 1","647$ puta više na L2, tj. oko 0,27 m. Zenitnih #br(B.iono_vrh_m) m iz simulatora u 14 h odgovara oko #br(B.iono_vrh_m / B.tecu_l1_m, d: 0) TECU, što je umjereno. Za vrijeme jakih geomagnetskih oluja vertikalni TEC može prijeći 100 TECU, tj. desetke metara na L1.
])[
  Koliko metara kasni L1, a koliko L2 za TEC od 1 TECU = $10^16$ el/m²? Koliki vertikalni TEC odgovara zenitnom kašnjenju od #br(B.iono_vrh_m) m u simulatoru?
]

#vjezba(vrsta: "vodjena", naslov: "Ionosfera u eksperimentu", rjesenje: [
  Kartica pokazuje dnevnu krivulju zenitnog kašnjenja s vrhom oko 14 h lokalnog vremena i noćnim pragom, koso kašnjenje po elevaciji (najveće pri horizontu) te ostatak iono-free kombinacije, praktično nulu. U živoj simulaciji pomicanje klizača doba dana ne mijenja vidljivo pogrešku položaja, jer prijemnik koristi iono-free kombinaciju (napomena u ovom poglavlju).
])[
  Otvori #ui("Eksperimenti…") i karticu #ui("Ionosfera"). Pokreni izračun za Zagreb i za mjesto blizu ekvatora. Pročitaj #ui("Vrh (dan)"), #ui("Noćni pod"), #ui("L1 @20°") i #ui("Iono-free rezidual"). Zatim u živoj simulaciji pomiči klizač #ui("Doba dana (ionosfera)") od noći do 14 h i prati #ui("Greška"). Objasni što vidiš.
]

#vjezba(vrsta: "vodjena", naslov: "Proračun pogreške jednog satelita", rjesenje: [
  Za svaki satelit pogled iznutra rastavlja pseudoudaljenost na sat prijemnika (ogroman i isti za sve satelite), Sagnac (do ±27 m, ovisno o azimutu), ISB (za GPS nula), eventualni kvar i troposferski ostatak (centimetri), a ostatak čine multipath i šum. Kod satelita nisko nad horizontom ostatak je redovito nekoliko puta veći nego kod satelita u zenitu, u skladu s @tab:budget. Pogreška efemerida duž linije pogleda je reda metra i mijenja se sporo, iz sekunde u sekundu gotovo jednako.
])[
  Pauziraj simulaciju, otvori #ui("Pogled iznutra (matematika epohe)…"), karticu #ui("1. Mjerenja"), i klikni redak satelita s najnižom elevacijom. U odjeljku #ui("Proračun greške mjerenja (zna samo simulator)") pročitaj sve članove. Ponovi za satelit s najvišom elevacijom. Koji se članovi razlikuju i zašto? Koliko je velika pogreška efemerida duž linije pogleda? Klikni #ui("Korak +1 s") i usporedi.
]

#vjezba(vrsta: "racunska", naslov: "Što ako model troposfere griješi?", rjesenje: [
  Pogreška modela od 10 % je 0,24 m u zenitu, ali 1,4 m na 10° i 2,75 m na 5°. Pogreška je za sve satelite istog predznaka i raste prema horizontu, pa je položaj najviše pogađa po *visini*: sat prijemnika upije zajednički dio, a ostatak se zbog asimetrije (svi sateliti su iznad nas) pretvori u pomak gore–dolje. Zato se u praksi za precizan rad niski sateliti izbacuju maskom elevacije ili se troposfera procjenjuje.
])[
  Pretpostavi da je model troposfere u prijemniku za 10 % pogrešan. Kolika je pogreška pseudoudaljenosti satelita u zenitu, na 10° i na 5°? Na koju komponentu položaja (istok, sjever, gore) će takva pogreška najviše utjecati i zašto?
]
