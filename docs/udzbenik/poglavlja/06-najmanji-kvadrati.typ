#import "../predlozak.typ": *
#let B = json("../skripte/brojke_06.json")

= Određivanje položaja metodom najmanjih kvadrata <pog:ls>

U prethodnim poglavljima smo vidjeli kako prijemnik iz signala dobiva *pseudoudaljenost* do svakog satelita i koje se pogreške u nju uvlače. Ovo poglavlje odgovara na središnje pitanje satelitske navigacije: kako iz nekoliko pseudoudaljenosti izračunati položaj. Odgovor je nelinearni sustav jednadžbi koji se rješava iterativno, metodom najmanjih kvadrata. Isti postupak koristi simulator pri „” prijemnika, prije nego što preuzme Kalmanov filtar (pogl. @pog:kalman).

== Jednadžba pseudoudaljenosti

Neka je $bold(x) = (x, y, z)$ nepoznati položaj prijemnika u sustavu ECEF, a $bold(s)_i$ položaj satelita $i$ izračunat iz navigacijske poruke. Prijemnik mjeri vrijeme leta signala svojim satom, koji nije sinkroniziran sa satelitima. Pogreška sata prijemnika $delta t$ pomnožena brzinom svjetlosti dodaje se *jednako* svim mjerenjima iste epohe:

$ rho_i = norm(bold(s)_i - bold(x)) + c dot delta t + epsilon_i , quad i = 1, dots, n $ <eq:pr>

Član $epsilon_i$ skuplja sve što nakon korekcija preostane: šum koda, multipath, ostatak troposfere i pogrešku efemerida (pogl. @pog:pogreske). Nepoznanice su četiri, $(x, y, z, b)$ uz pokratu $b = c dot delta t$, pa trebamo *barem četiri satelita*. To je razlog zbog kojeg se u GPS-u stalno ponavlja broj četiri: tri satelita ne bi bila dovoljna, jer sat prijemnika nije atomski.

#napomena(naslov: "Koliko je velik b?")[
  U simulatoru sat prijemnika ima namjerni drift od $10^(-6)$ s/s. Pomak $b$ zato raste za oko *#br(B.drift_sata_m_po_s, d: 0) m svake sekunde*, što je izmjereno iz rješenja u 600 uzastopnih epoha. Nakon deset minuta $b$ iznosi oko #br(B.drift_sata_m_po_s * 0.6, d: 0) km. To nije problem, jer je $b$ samo još jedna nepoznanica koja se procjenjuje u svakoj epohi. Problem bi nastao kad bismo ga pokušali zanemariti.
]

U simulatoru @eq:pr ima još jedan, poznati član: Sagnacovu korekciju, koja opisuje rotaciju Zemlje tijekom oko 70 ms leta signala (pogl. @pog:koordinate). Prijemnik je računa iz procjene položaja i dodaje modelu, pa je u izvodima koji slijede izostavljamo radi preglednosti.

== Linearizacija

Jednadžba @eq:pr je nelinearna u $bold(x)$ zbog norme. Pretpostavimo da imamo približno rješenje $hat(bold(x))_0, hat(b)_0$ i razvijmo model u Taylorov red do prvog člana. Predviđena pseudoudaljenost i njezine derivacije su

$ hat(rho)_i = norm(bold(s)_i - hat(bold(x))_0) + hat(b)_0 , quad
  (partial rho_i) / (partial bold(x)) = (hat(bold(x))_0 - bold(s)_i)^T / norm(bold(s)_i - hat(bold(x))_0) = -bold(e)_i^T , quad
  (partial rho_i) / (partial b) = 1 , $

gdje je $bold(e)_i$ jedinični vektor *od prijemnika prema satelitu*. Razliku izmjerene i predviđene pseudoudaljenosti $y_i = rho_i - hat(rho)_i$ zovemo *rezidual prije rješenja* (u Kalmanovom filtru: *inovacija*). Za cijelu epohu dobivamo linearni sustav

$ bold(y) = bold(G) delta bold(x) + bold(epsilon), quad
  bold(G) = mat(-bold(e)_1^T, 1; dots.v, dots.v; -bold(e)_n^T, 1) in RR^(n times 4) , $ <eq:lin>

u kojem je $delta bold(x) = (delta x, delta y, delta z, delta b)$ popravak približnog rješenja. Matrica $bold(G)$ je *matrica geometrije*. Ona ovisi samo o smjerovima prema satelitima, a ne o samim mjerenjima. U poglavlju @pog:dop ćemo vidjeti da iz nje izravno slijedi koliko se pogreška mjerenja pojačava u pogrešku položaja.

== Rješenje najmanjih kvadrata i Gauss-Newtonova iteracija

Kad je satelita više od četiri, sustav @eq:lin je preodređen i nema egzaktnog rješenja. Tražimo $delta bold(x)$ koji minimizira zbroj kvadrata ostataka $norm(bold(y) - bold(G) delta bold(x))^2$. Izjednačavanjem gradijenta s nulom dobivamo *normalne jednadžbe*:

$ bold(G)^T bold(G) delta bold(x) = bold(G)^T bold(y) quad => quad
  delta hat(bold(x)) = (bold(G)^T bold(G))^(-1) bold(G)^T bold(y) . $ <eq:ls>

Budući da je model lineariziran, jedan korak nije dovoljan. Popravljeno rješenje $hat(bold(x))_1 = hat(bold(x))_0 + delta hat(bold(x))$ postaje nova točka linearizacije i postupak se ponavlja dok popravak ne postane zanemariv. To je *Gauss-Newtonova metoda*. Simulator staje kad je $norm(delta bold(x)) < 1$ m (funkcija #kod("Receiver.solve_position")).

Zanimljivo je koliko je ta iteracija robusna. Prijemnik u simulatoru kreće od *središta Zemlje*, $hat(bold(x))_0 = (0, 0, 0)$, $hat(b)_0 = 0$, i unatoč tome konvergira u nekoliko koraka (@fig:gn). U primjeru sa #B.gn_n_sat satelita iznad Zagreba udaljenost od prave pozicije pada redom #br(B.gn_greske_m.at(0) / 1000, d: 0) km → #br(B.gn_greske_m.at(1) / 1000, d: 0) km → #br(B.gn_greske_m.at(2) / 1000, d: 1) km → #br(B.gn_greske_m.at(3), d: 0) m → #br(B.gn_greske_m.at(4), d: 1) m, nakon čega se više ne mijenja. Preostalih #br(B.gn_greske_m.at(4), d: 1) m nije pogreška metode nego pogreška samih mjerenja $epsilon_i$.

#figure(
  image("../slike/06-gauss-newton.svg", width: 88%),
  caption: [Konvergencija Gauss-Newtonove iteracije iz središta Zemlje (Zagreb, jedna epoha, #B.gn_n_sat satelita, sjeme 6). Log-skala: pogreška se u blizini rješenja gotovo kvadrira u svakom koraku, sve do razine šuma mjerenja.],
) <fig:gn>

Zašto metoda radi čak i iz tako loše početne točke? Sateliti su oko 20 000 km od Zemlje, pa su smjerovi $bold(e)_i$ prema njima iz središta Zemlje i s površine slični: linearizacija je dobra već u prvom koraku. Za prijemnik na Zemlji s druge strane planeta ne bi bilo tako.

== Točno četiri satelita i redundancija

Kad je $n = 4$, matrica $bold(G)$ je kvadratna i (uz dobru geometriju) regularna, pa @eq:ls daje egzaktno rješenje $delta hat(bold(x)) = bold(G)^(-1) bold(y)$. Ostaci su tada *točno nula*: mjerenja se savršeno slažu s rješenjem *bez obzira na to koliko su pogrešna*. Ako je jedan od četiri satelita pokvaren, rješenje je pogrešno, a ništa u podacima to ne otkriva.

S pet i više satelita postoji *višak mjerenja* (redundancija $n - 4$). Ostaci $bold(r) = bold(y) - bold(G) delta hat(bold(x))$ tada nose informaciju o tome koliko su mjerenja međusobno dosljedna. Upravo na tome počiva provjera integriteta RAIM (pogl. @pog:raim): s jednim viškom kvar se može *otkriti*, a s dva i više može se i *izolirati*.

#kljucno[
  - Četiri satelita daju *rješenje*. Pet i više daju i *provjeru* tog rješenja.
  - Ostaci najmanjih kvadrata nisu pogreške položaja. Oni mjere nedosljednost mjerenja.
]

== Težinski najmanji kvadrati

Nisu sva mjerenja jednako dobra. Satelit nisko nad horizontom ima slabiji signal (niži C/N0, pogl. @pog:signal), dulji put kroz atmosferu i više multipatha. Ako je poznata standardna devijacija $sigma_i$ svakog mjerenja, optimalno je mjerenja otežati s $W = "diag"(1 \/ sigma_i^2)$:

$ delta hat(bold(x)) = (bold(G)^T bold(W) bold(G))^(-1) bold(G)^T bold(W) bold(y) . $ <eq:wls>

Ako su pogreške neovisne, nepristrane i Gaussove, ovo je procjenitelj najmanje varijance (Gauss-Markovljev teorem). Simulator $sigma_i$ računa iz dva dijela (#kod("receiver.meas_sigma")):

$ sigma_i^2 = sigma_("kod")("C/N0"_i)^2 + ((0","8 "m") / (sin "el"_i))^2 . $ <eq:sigma>

Prvi član je termalni šum petlje koda (DLL) iono-free kombinacije, izračunat iz izmjerenog C/N0. Pravi prijemnici ga daju kao procjenu točnosti mjerenja. Drugi član opisuje sve što C/N0 ne vidi: pogrešku efemerida, multipath i ostatak troposfere, koji rastu prema horizontu.

@fig:wls uspoređuje obični i težinski LS na istim mjerenjima kroz 600 epoha. Dobitak je vidljiv, ali skroman: horizontalna pogreška p95 pada s #br(B.ls.h95) m na #br(B.wls.h95) m (medijan s #br(B.ls.h50, d: 2) m na #br(B.wls.h50, d: 2) m). Razlog je dvojak. Sateliti u rješenju razlikuju se po $sigma_i$ najviše nekoliko puta, pa težine ne mijenjaju sliku iz temelja. Osim toga, dio pogreške (sporo promjenjiva pogreška efemerida, multipath) nije ni neovisan ni bijeli, pa pretpostavke Gauss-Markovljevog teorema vrijede samo približno. Težine postaju važne kad se kvaliteta mjerenja jako razlikuje, primjerice pod ometanjem (pogl. @pog:napadi).

#figure(
  image("../slike/06-ls-vs-wls.svg", width: 96%),
  caption: [Horizontalna pogreška običnog i težinskog LS-a na istim mjerenjima (Zagreb, samo GPS, 600 epoha, sjeme 6). Iscrtkana kružnica obuhvaća 95 % epoha.],
) <fig:wls>

== Kako to radi simulator

Prijemnik u simulatoru (#kod("receiver.py")) koristi najmanje kvadrate samo jednom, za *hladni start*. U prvoj epohi u kojoj ima barem četiri mjerenja rješava @eq:lin Gauss-Newtonom iz središta Zemlje. Dobivenim položajem i satom zatim inicijalizira 11-dimenzionalni Kalmanov filtar, koji od tada radi sam (pogl. @pog:kalman). Istraživački sandbox ima i čisti snapshot procjenitelj #kod("wls") s istim modelom mjerenja i vlastitim RAIM-om, kojim se u poglavlju @pog:projekti uspoređuje s filtrom.

Međuveličine jedne epohe vide se u prozoru #ui("Pogled iznutra (matematika epohe)…") u lijevom panelu. Kartica #ui("1. Mjerenja") prikazuje za svaki satelit izmjerenu i predviđenu pseudoudaljenost te njihovu razliku. Kartica #ui("2. Geometrija") prikazuje matricu $bold(G)$ u lokalnom sustavu istok–sjever–gore.

#vjezba(vrsta: "vodjena", naslov: "Matrica geometrije uživo", rjesenje: [
  Redaka ima onoliko koliko je satelita u rješenju (uz 6–10 satelita samo GPS-a). Prva tri stupca su komponente jediničnog vektora istok–sjever–gore, pa za svaki redak vrijedi $e_E^2 + e_N^2 + e_U^2 = 1$. Satelit visoko na nebu ima stupac „” blizu 1, a satelit pri horizontu blizu 0. Četvrti stupac (sat) je uvijek 1. Nakon jedne sekunde brojevi se mijenjaju tek u trećoj ili četvrtoj decimali, jer se satelit u sekundi pomakne za 3–4 km, a to je na udaljenosti od 20 000 km kut od oko 0,01°.
])[
  Postavi prijemnik dvoklikom na globus (npr. na Zagreb), pokreni simulaciju gumbom #ui("Pokreni") i otvori #ui("Pogled iznutra (matematika epohe)…"). Na kartici #ui("2. Geometrija") pronađi matricu $bold(G)$.
  + Koliko ima redaka, a koliko stupaca? Što predstavlja koji stupac?
  + Provjeri za dva retka da je zbroj kvadrata prva tri broja jednak 1. Zašto?
  + Usporedi redak satelita s najvećom i najmanjom elevacijom (kartica #ui("1. Mjerenja")). Koji se stupac najviše razlikuje?
  + Klikni #ui("Zamrzni (pauza)"), pa #ui("Korak +1 s"). Koliko se promijenila matrica?
]

#vjezba(vrsta: "racunska", naslov: "Derivacija udaljenosti", rjesenje: [
  $partial / (partial bold(x)) norm(bold(s) - bold(x)) = partial / (partial bold(x)) sqrt((bold(s)-bold(x))^T (bold(s)-bold(x))) = (-(bold(s) - bold(x))^T) / norm(bold(s) - bold(x)) = -bold(e)^T$. Predznak je negativan jer se pomakom prijemnika *prema* satelitu udaljenost smanjuje.
])[
  Izvedi $partial norm(bold(s) - bold(x)) \/ partial bold(x)$ i objasni predznak. Zašto je derivacija po $b$ jednaka 1 za svaki satelit?
]

#vjezba(vrsta: "racunska", naslov: "Vlastiti Gauss-Newton", rjesenje: [
  Iteracija iz $(0, 0, 0, 0)$ konvergira u 4–5 koraka. U odnosu na pravi položaj (u ECEF: pretvori 45,815° N, 15,982° E, 120 m) rješenje sa svih šest satelita odstupa za (#br(B.vjezba_6sat_enu_m.at(0), d: 2); #br(B.vjezba_6sat_enu_m.at(1), d: 2); #br(B.vjezba_6sat_enu_m.at(2), d: 2)) m (istok, sjever, gore), a procijenjeni $b$ = #br(B.vjezba_6sat_cb_m, d: 2) m. Ako je tvoj rezultat drugačiji za desetke metara, provjeri jesi li dodao Sagnacovu korekciju: $omega_E (s_x y - s_y x) \/ c$ (gdje su $s_x, s_y$ koordinate satelita, a $x, y$ prijemnika), uz $omega_E = 7","292 space 115 space 9 dot 10^(-5)$ rad/s. Bez nje rješenje se pomiče prema istoku. Rješenje samo s prva četiri satelita odstupa #br(B.vjezba_4sat_greska_m, d: 2) m, a ostaci su na razini zaokruživanja ($< 10^(-6)$ m): četiri jednadžbe s četiri nepoznanice zadovoljene su točno, pa podaci ne mogu otkriti koliko je rješenje pogrešno.
])[
  Datoteka #kod("docs/udzbenik/podaci/epoha_zagreb.csv") sadrži jednu epohu iz simulatora: ECEF položaje šest satelita (iz navigacijske poruke), pseudoudaljenosti s već primijenjenim korekcijama ionosfere i troposfere te $sigma_i$ prema @eq:sigma. Prijemnik je stajao na 45,815° N, 15,982° E, 120 m.
  + U Pythonu (numpy) napiši Gauss-Newtonovu iteraciju prema @eq:ls s modelom $hat(rho)_i = norm(bold(s)_i - bold(x)) + b + "Sagnac"_i$. Kreni od $(0, 0, 0, 0)$.
  + Ispiši $norm(delta bold(x))$ po iteracijama. Koliko koraka treba?
  + Pretvori pogrešku u lokalni sustav istok–sjever–gore (pogl. @pog:koordinate).
  + Ponovi samo s prva četiri satelita i ispiši ostatke. Što primjećuješ?
]

#vjezba(vrsta: "vodjena", naslov: "Četiri satelita nisu dosta za provjeru", rjesenje: [
  Dok ima pet i više satelita, status integriteta je „”. S točno pet satelita RAIM može otkriti kvar, ali ga ne može izolirati (jedan stupanj slobode). Kad ostanu četiri, status postaje #ui("nedostupan (premalo satelita)"): rješenje postoji, ali ga se ne može provjeriti. Pogreška obično naraste, a GDOP skoči jer preostali sateliti pokrivaju manji dio neba. S tri satelita fix nestaje.
])[
  U panelu #ui("Sustavi") ostavi samo GPS. U tablici #ui("Sateliti u vidokrugu") isključuj satelite jedan po jedan (kružić ●/○ na početku retka) dok ne ostanu četiri.
  + Prati redak #ui("Integritet") u telemetriji. Kako se mijenja status kad ostane šest, pet i četiri satelita?
  + Što se događa s pogreškom i GDOP-om? Usporedi s gornjim odjeljkom o redundanciji.
  + Isključi još jedan satelit. Što se događa?
]

#vjezba(vrsta: "racunska", naslov: "Zašto težine?", rjesenje: [
  Iz @eq:sigma, uz $sigma_("kod") = 2","5$ m u zenitu: $sigma(90°) = sqrt(2","5^2 + 0","8^2) approx 2","6$ m. Na 10° je $0","8 \/ sin 10° = 4","6$ m, pa uz $sigma_("kod") approx 6$ m (niži C/N0) dobivamo $sigma approx 7","6$ m. Omjer težina je $(7","6 \/ 2","6)^2 approx 8","5$, pa jedno zenitno mjerenje vrijedi kao osam do devet mjerenja pri horizontu.
])[
  Pretpostavi da je šum koda $sigma_("kod")$ 2,5 m u zenitu i 6 m na elevaciji 10°. Prema @eq:sigma izračunaj $sigma_i$ za oba slučaja i omjer njihovih težina u @eq:wls. Koliko mjerenja pri horizontu „” jedno zenitno mjerenje?
]
