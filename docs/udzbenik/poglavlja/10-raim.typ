#import "../predlozak.typ": *
#let B = json("../skripte/brojke_10.json")
#let R = B.roc
#let pd(pfa, x) = R.at(pfa).filter(p => p.x == x).first().raim_pd

= Integritet: RAIM i zaštitne granice <pog:raim>


#cilj(
  [razliku između točnosti i integriteta te pojmove HAL, HPL, MI i HMI],
  [kako RAIM statističkim testom otkriva i isključuje kvar],
  [kako se računa zaštitna granica i koliko je RAIM osjetljiv],
  [što RAIM u načelu ne može vidjeti],
)

Točnost odgovara na pitanje koliko je prijemnik obično blizu istine. Za pilota, brodara ili autonomno vozilo važnije je drugo pitanje: *smijem li ovoj procjeni vjerovati sada?* Sustav koji je 99 % vremena točan na metar, a ostatak vremena bez upozorenja pogriješi za kilometar, opasniji je od sustava koji je uvijek točan na 50 m i pouzdano javi kad nije. Ovo poglavlje uvodi *integritet* i njegovu najstariju autonomnu provjeru u prijemniku, RAIM (_receiver autonomous integrity monitoring_).

== Rječnik integriteta

- *Granica uzbune* HAL (VAL za visinu): najveća pogreška koju operacija smije podnijeti. Za neprecizni prilaz zrakoplova (RNP 0.3) HAL je 0,3 nautičke milje = #br(B.hal, d: 0) m. To je zadana vrijednost u simulatoru.
- *Zaštitna granica* HPL (VPL): prijemnikova gornja procjena vlastite pogreške, izračunata tako da je vjerojatnost da stvarna pogreška bude veća, a da to nije javljeno, zanemariva.
- *Integritet je dostupan* kada je HPL ≤ HAL. Inače prijemnik mora reći da ne može jamčiti zahtjeve, čak i kad je trenutna pogreška mala.
- *Lažna informacija* (MI, _misleading information_): pogreška veća od HPL-a bez alarma. *Opasna lažna informacija* (HMI): pogreška veća i od HAL-a, uz HPL ≤ HAL i bez alarma. HMI je ono što integritet mora spriječiti.

== Detekcija: test reziduala

RAIM koristi redundanciju iz poglavlja @pog:ls. Uz težine $bold(W) = "diag"(1\/sigma_i^2)$ rješenje težinskih najmanjih kvadrata ostavlja rezidual

$ bold(r) = bold(y) - bold(G) delta hat(bold(x)) = (bold(I) - bold(G) (bold(G)^T bold(W) bold(G))^(-1) bold(G)^T bold(W)) bold(y) = bold(S) bold(y) . $ <eq:rez>

Matrica $bold(S)$ projicira mjerenja na dio koji geometrija *ne može objasniti*. Ako nema kvara i ako su $sigma_i$ točne, testna statistika

$ T = bold(r)^T bold(W) bold(r) $ <eq:test>

ima χ² razdiobu s $n - m$ stupnjeva slobode, gdje je $n$ broj mjerenja, a $m$ broj nepoznanica (4 za jedan sustav, plus jedan sat po dodatnom sustavu). Prag $T_d$ bira se tako da je vjerojatnost lažnog alarma u epohi bez kvara $P_"FA"$. Simulator koristi $P_"FA" = 10^(-5)$, što daje $T_d$ = #br(B.prag.at("1")) za jedan, #br(B.prag.at("4")) za četiri i #br(B.prag.at("6")) za šest stupnjeva slobode.

#figure(
  image("../slike/10-chi2.svg", width: 90%),
  caption: [Razdioba testne statistike bez kvara (χ² s 4 stupnja slobode) i s kvarom one veličine koja se propusti s vjerojatnošću $P_"MD" = 10^(-3)$ (necentralni χ²). Iscrtkano: prag za $P_"FA" = 10^(-5)$. Log-mjerilo.],
) <fig:chi2>

Ključna pretpostavka je da prijemnik zna stvarnu razinu šuma. Ako podcjenjuje $sigma_i$, test pali lažne alarme. Ako ih precjenjuje, propušta kvarove. @fig:kal provjerava simulator: u #B.kal.epoha čistih epoha (tri sjemena × 30 min, Zagreb, samo GPS) statistika $T$ za najčešći slučaj od #B.kal.dof stupnja slobode ima srednju vrijednost #br(B.kal.sred_T, d: 2), uz očekivanih #B.kal.dof. Omjer $T\/T_d$ u 99 % epoha ostaje ispod #br(B.kal.omjer_p99, d: 2), a najveći je #br(B.kal.omjer_max, d: 2). Nijedna epoha nije javila kvar ili isključila satelit.

#figure(
  image("../slike/10-kalibracija.svg", width: 86%),
  caption: [Histogram testne statistike u čistoj simulaciji i teorijska χ² razdioba. Model šuma prijemnika (C/N0 i elevacija, @eq:sigma) dobro odgovara stvarnom šumu, pa je test ispravno kalibriran.],
) <fig:kal>

== Isključivanje kvara (FDE)

Kad je $T > T_d$, nešto nije u redu. Ako je redundancija barem dva ($n - m >= 2$), prijemnik može pokušati *izolirati* krivca. Simulator isključuje mjerenje s najvećim normaliziranim rezidualom $|r_i| \/ (sigma_i sqrt(S_(i i)))$ i ponavlja test. Ako nakon toga test prolazi, status je #ui("kvar isključen"). S redundancijom jedan kvar se može samo otkriti, a status je #ui("KVAR — ne može se izolirati"). Bez redundancije integritet je #ui("nedostupan (premalo satelita)").

Prijemnik u simulatoru ima i prvi, grubi stupanj: prije statističkog testa iterativno izbacuje mjerenja čija inovacija od medijane odstupa za više od šest robusnih standardnih devijacija (MAD) *i* više od 600 m. Takve kilometarske greške inače bi pokvarile samu linearizaciju. Taj je stupanj, primjerice, zadužen za ugrađeni pokazni kvar idealizirane konstelacije, gdje jedan satelit nakon 200 s dobije pogrešku sata od 6 km. U živoj aplikaciji taj je kvar isključen.

== Zaštitne granice

Kolika može biti pogreška položaja zbog kvara na satelitu $i$ koji test još *ne* otkriva? Kvar veličine $f_i$ pomiče rješenje za $bold(K)_(:,i) f_i$, gdje je $bold(K) = (bold(G)^T bold(W) bold(G))^(-1) bold(G)^T bold(W)$, a testnu statistiku za $f_i^2 S_(i i) \/ sigma_i^2$. Omjer horizontalnog pomaka i korijena porasta statistike je *nagib* (_slope_) satelita:

$ "Hslope"_i = sqrt(K_(E,i)^2 + K_(N,i)^2) dot sigma_i / sqrt(S_(i i)) . $ <eq:slope>

Neka je $lambda$ necentralni parametar za koji necentralna χ² razdioba ostaje ispod praga s vjerojatnošću $P_"MD" = 10^(-3)$ (@fig:chi2). Za četiri stupnja slobode $lambda$ = #br(B.lambda.at("4")). Tada je

$ "HPL" = max_i "Hslope"_i dot sqrt(lambda) , $ <eq:hpl>

a VPL se računa analogno s komponentom $K_(U,i)$. Satelit s najvećim nagibom je onaj čiji kvar najviše pomiče položaj, a najmanje se vidi u rezidualu. Obično je to satelit koji sam određuje neki smjer, jer nema „svjedoka”. U čistoj simulaciji iz Zagreba (samo GPS) medijan HPL-a je #br(B.kal.hpl_med, d: 0) m, a 95 % epoha ima HPL ispod #br(B.kal.hpl_p95, d: 0) m, desetak puta više od stvarne pogreške. Zaštitna granica je namjerno konzervativna.

Na globusu simulatora HPL je krug oko procijenjenog položaja: zelen kad je integritet dostupan, a crven kad je javljen alarm ili je HPL veći od HAL-a.

== Primjer: kvar koji polako raste

Najteži kvarovi nisu skokovi od kilometra, nego oni koji rastu polako. @fig:rampa prikazuje satelit čiji sat od $t$ = 120 s počinje bježati brzinom 0,5 m/s. Bez RAIM-a pogreška položaja raste zajedno s kvarom i na kraju, uz kvar od #br(B.rampa.kvar_kraj_m, d: 0) m, iznosi #br(B.rampa.bez_eh_kraj, d: 0) m. S RAIM-om test raste dok u $t$ = #B.rampa.prvo_iskljucenje_s s, uz kvar od #br(B.rampa.kvar_pri_iskljucenju_m) m, ne prijeđe prag. Satelit se tada isključi, a pogreška se vrati na #br(B.rampa.raim_eh_kraj) m.

#figure(
  image("../slike/10-rampa.svg", width: 96%),
  caption: [Kvar sata jednog satelita koji raste 0,5 m/s od $t$ = 120 s (siva linija). Gore: horizontalna pogreška bez RAIM-a i s RAIM-om te HPL. Dolje: omjer testne statistike i praga. Crvena linija označava prvo isključenje.],
) <fig:rampa>

== Koliko je RAIM osjetljiv?

Studija u sandboxu (#kod("sandbox/examples/raim_roc.json"), Zagreb, samo GPS, 10 sjemena × 120 s) ubacuje stalni kvar sata različite veličine na slučajno odabrani satelit i mjeri vjerojatnost detekcije po epohi za tri razine lažnog alarma (@fig:roc). Uz $P_"FA" = 10^(-4)$ kvar od 10 m otkriva se u #br(pd("0.0001", 10) * 100, d: 0) % epoha, od 30 m u #br(pd("0.0001", 30) * 100, d: 0) %, a od 60 m u #br(pd("0.0001", 60) * 100, d: 0) %. Stroži prag ($10^(-7)$) gotovo eliminira lažne alarme, ali za istu vjerojatnost detekcije traži otprilike upola veći kvar: polovicu epoha otkriva tek kvar od 30 do 45 m (#br(pd("1e-07", 30) * 100, d: 0) % uz 30 m, #br(pd("1e-07", 45) * 100, d: 0) % uz 45 m). Uz $P_"FA" = 10^(-2)$ izmjerena stopa lažnih alarma bez kvara je upravo #br(R.at("0.01").first().false_alarm_rate * 100, d: 1) %, kako i treba.

#figure(
  image("../slike/10-roc.svg", width: 88%),
  caption: [Vjerojatnost detekcije kvara po epohi u ovisnosti o veličini kvara sata jednog satelita, za tri vjerojatnosti lažnog alarma (sandbox, EKF, srednja vrijednost preko 10 sjemena).],
) <fig:roc>

Kvar od nekoliko metara RAIM ne vidi. To je u redu, jer takav kvar ne pomiče položaj izvan HPL-a. Upravo to jamči konstrukcija zaštitne granice.

== Granice RAIM-a

RAIM pretpostavlja da je *najviše jedan* satelit pokvaren i da su ostali zdravi. Kad su pokvarena dva ili više njih na *dosljedan* način, rezidual može ostati malen. Krajnji slučaj je koordinirani lažni signal (pogl. @pog:napadi): svi sateliti „lažu” usklađeno, tako da rješenje glatko odluta prema cilju napadača, a $T$ ostaje nizak. RAIM ga u načelu ne može otkriti. To nije pogreška simulatora, nego temeljno ograničenje svake provjere koja se oslanja samo na međusobnu dosljednost mjerenja.

Zato zrakoplovstvo za strože operacije koristi vanjsku provjeru integriteta (SBAS, npr. EGNOS) ili napredni RAIM (ARAIM) s više sustava i eksplicitnim modelom višestrukih kvarova.

#kljucno[
  - Integritet nije točnost. To je sposobnost da se pravovremeno kaže „ne vjeruj mi”.
  - RAIM testira dosljednost redundantnih mjerenja. Treba barem jedno mjerenje viška za detekciju i dva za isključivanje.
  - HPL je gornja granica pogreške uz pretpostavku jednog kvara. Konzervativna je i ne vrijedi za usklađene laži.
]

#vjezba(vrsta: "vodjena", naslov: "Ubrizgaj kvar", rjesenje: [
  Kvar od 30 m otkriva se otprilike u svakoj drugoj epohi (usporedi @fig:roc): status povremeno prelazi u #ui("kvar isključen"), a satelit u tablici tada postaje #ui("RAIM odbacio"). Kvar od 60 m isključuje se gotovo u svakoj epohi, a pogreška položaja ostaje nekoliko metara. Kvar od 5 m obično prolazi neotkriven, a pogreška naraste tek za metar ili dva, jer je mali u odnosu na šum. Kad uz pet satelita ubrizgaš 100 m, status postaje #ui("KVAR — ne može se izolirati"): test vidi kvar, ali s jednim stupnjem slobode ne zna koji je satelit kriv, pa se položaj ne može popraviti.
])[
  Uz samo GPS i RAIM uključen otvori editor satelita koji se koristi u rješenju. U #ui("Greška sata (kvar) [m]") upiši 30. Prati redak #ui("Integritet"), krug HPL-a na globusu i #ui("Greška") barem minutu simulacije. Ponovi s kvarovima od 60 m i 5 m. Zatim isključi satelite dok ih ne ostane pet i ubrizgaj 100 m. Na kraju poništi kvar gumbom #ui("Zdrav (poništi kvarove)").
]

#vjezba(vrsta: "vodjena", naslov: "RAIM iznutra", rjesenje: [
  Kartica prikazuje $T$, prag $T_d$, broj stupnjeva slobode i $lambda$, krivulju χ² s označenim pragom te za svaki satelit normalizirani rezidual i nagib. Bez kvara $T$ je redovito daleko lijevo od praga. Satelit s najvećim nagibom je obično onaj koji sam pokriva neki dio neba. Njegovim isključivanjem HPL naraste više nego isključivanjem bilo kojeg drugog satelita. Pri kvaru od 30 m normalizirani rezidual pokvarenog satelita iskoči, a nakon isključenja nestaje iz izračuna.
])[
  Otvori #ui("Pogled iznutra (matematika epohe)…") i karticu #ui("4. RAIM"). Pronađi $T$, $T_d$, broj stupnjeva slobode i $lambda$. Koji satelit ima najveći nagib i zašto? Ubrizgaj kvar od 30 m na jedan satelit i promotri kako se mijenjaju normalizirani reziduali.
]

#vjezba(vrsta: "racunska", naslov: "Projekcijska matrica", rjesenje: [
  Uz $bold(P) = bold(G)(bold(G)^T bold(W) bold(G))^(-1) bold(G)^T bold(W)$ vrijedi $bold(P)^2 = bold(P)$, pa je $bold(S) = bold(I) - bold(P)$ također idempotentna: $bold(S)^2 = bold(I) - 2 bold(P) + bold(P)^2 = bold(S)$. Trag projektora jednak je rangu: $"tr"(bold(P)) = m$, pa je $"tr"(bold(S)) = n - m$. Zato je $E[T] = n - m$ za normirane pogreške, što je srednja vrijednost χ² razdiobe s $n - m$ stupnjeva slobode. Uz $n = 4$ i $m = 4$ je $bold(S) = 0$: rezidual je uvijek nula i kvar se ne vidi (pogl. @pog:ls).
])[
  Pokaži da je $bold(S)$ iz @eq:rez idempotentna ($bold(S)^2 = bold(S)$) i da je $"tr"(bold(S)) = n - m$. Što iz toga slijedi za očekivanu vrijednost $T$? Što je $bold(S)$ kad je $n = m$?
]

#vjezba(vrsta: "racunska", naslov: "Prag i zaštitna granica", rjesenje: [
  (a) Iz tablice χ² razdiobe (ili #kod("raim.chi2_isf(1e-5, k)")): $T_d$ = #br(B.prag.at("1")), #br(B.prag.at("2")), #br(B.prag.at("4")), #br(B.prag.at("6")) i #br(B.prag.at("8")) za 1, 2, 4, 6 i 8 stupnjeva slobode. Prag raste jer zbroj više kvadrata prirodno ima veću vrijednost. (b) $lambda$ raste sporije, od #br(B.lambda.at("1")) do #br(B.lambda.at("8")). Uz najveći nagib od 5 m dobivamo HPL $= 5 sqrt(#br(B.lambda.at("4"))) approx #br(5 * calc.sqrt(B.lambda.at("4")), d: 0)$ m za četiri stupnja slobode. (c) Uz $P_"FA" = 10^(-7)$ prag i $lambda$ rastu, pa je HPL veći: manje lažnih alarma plaća se slabijom zaštitom.
])[
  (a) Pomoću #kod("raim.chi2_isf") izračunaj prag $T_d$ za $P_"FA" = 10^(-5)$ i 1, 2, 4, 6 i 8 stupnjeva slobode. Zašto raste? (b) Pomoću #kod("raim.noncentrality") izračunaj $lambda$ za $P_"MD" = 10^(-3)$ i HPL ako je najveći nagib 5 m. (c) Kako se mijenja HPL ako se $P_"FA"$ smanji na $10^(-7)$?
]

#vjezba(vrsta: "istrazivacka", naslov: "ROC krivulja", rjesenje: [
  Rezultati su na @fig:roc. Uz kvar od 60 m detekcija je za $P_"FA" >= 10^(-4)$ gotovo sigurna (#br(pd("0.0001", 60) * 100, d: 0) % epoha). Stopa ispravnog isključivanja (#kod("correct_exclusion_rate")) zaostaje za vjerojatnošću detekcije, jer se pri malim kvarovima ponekad isključi pogrešan satelit. Za dodatnu studiju s rampom kvara koristi #kod("\"rate_mps\"") u napadu #kod("sat_fault").
])[
  Pokreni #kod("python sandbox.py run sandbox/examples/raim_roc.json --workers 4 --plot"). Usporedi #kod("raim_pd") i #kod("correct_exclusion_rate"). Zašto se razlikuju? Zatim osmisli studiju u kojoj kvar raste brzinom (#kod("rate_mps")) 0,1, 0,5 i 2 m/s i mjeri #kod("time_to_detect") i #kod("mi_events"). Koliki kvar je dosegnut u trenutku detekcije?
]
