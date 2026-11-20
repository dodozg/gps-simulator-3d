#import "../predlozak.typ": *
#let B = json("../skripte/brojke_08.json")
#let qs(scen, f) = B.q_studija.at(scen).filter(x => x.f == f).first()

= Kalmanov filtar <pog:kalman>

Najmanji kvadrati rješavaju svaku epohu kao da prije nje ništa nije bilo. Prijemnik se ipak ne može pomaknuti 10 m u sekundi kad stoji na stolu, a njegov sat ne može preskočiti kilometar ako je u prošloj epohi lutao 300 m/s. Kalmanov filtar spaja znanje o tome kako se stanje mijenja s novim mjerenjima. Optimalno je to za linearne sustave s Gaussovim šumom, a za GNSS se koristi njegova linearizirana inačica, prošireni Kalmanov filtar (EKF). Simulator ga koristi kao glavni navigacijski procesor.

== Vektor stanja i model gibanja

Prijemnik u simulatoru procjenjuje 11 veličina (#kod("receiver.py")):

$ bold(x) = (x, y, z, space v_x, v_y, v_z, space b, dot(b), space "ISB"_"GAL", "ISB"_"GLO", "ISB"_"BDS") , $ <eq:stanje>

redom položaj i brzinu u ECEF-u, pomak i drift sata u metrima ($b = c delta t$) te tri pomaka između vremenskih skala sustava (pogl. @pog:multignss). Model gibanja je *stalna brzina* i *stalni drift*: u vremenu $Delta t$

$ bold(x)_(k+1) = bold(F) bold(x)_k + bold(w)_k , quad
  bold(F) = mat(bold(I)_3, Delta t bold(I)_3, 0, 0; 0, bold(I)_3, 0, 0; 0, 0, mat(1, Delta t; 0, 1), 0; 0, 0, 0, bold(I)_3) , $ <eq:F>

gdje je $bold(w)_k$ procesni šum s kovarijancom $bold(Q) Delta t$. Ta kovarijanca kaže koliko model *ne* vjeruje sam sebi. Simulator koristi dijagonalni $bold(Q)$ sa spektralnim gustoćama: #B.Q.pos m²/s za položaj, #B.Q.vel (m/s)²/s za brzinu, #B.Q.bias m²/s za pomak sata, #B.Q.drift (m/s)²/s za drift i #B.Q.isb m²/s za ISB, koji je gotovo stalan.

== Predikcija i ažuriranje

Filtar u svakoj epohi radi dva koraka.

*Predikcija* pomiče procjenu i njezinu kovarijancu $bold(P)$ modelom gibanja:

$ hat(bold(x))^- = bold(F) hat(bold(x)) , quad bold(P)^- = bold(F) bold(P) bold(F)^T + bold(Q) Delta t . $ <eq:predikcija>

*Ažuriranje* uspoređuje izmjerene pseudoudaljenosti s predviđenima. Za satelit $i$ predviđena pseudoudaljenost je $h_i(hat(bold(x))^-) = norm(bold(s)_i - hat(bold(r))^-) + hat(b)^- + "Sagnac"_i + "ISB"_s$, a razlika $y_i = rho_i - h_i$ je *inovacija*: jedina nova informacija koju epoha donosi. Uz Jacobijevu matricu $bold(H)$ (retci kao u matrici $bold(G)$, pogl. @pog:ls, s jedinicom u stupcu sata i stupcu ISB-a tog sustava) i kovarijancu mjerenja $bold(R) = "diag"(sigma_i^2)$ prema @eq:sigma:

$ bold(S) = bold(H) bold(P)^- bold(H)^T + bold(R) , quad
  bold(K) = bold(P)^- bold(H)^T bold(S)^(-1) , $
$ hat(bold(x)) = hat(bold(x))^- + bold(K) bold(y) , quad
  bold(P) = (bold(I) - bold(K) bold(H)) bold(P)^- . $ <eq:azuriranje>

*Kalmanovo pojačanje* $bold(K)$ odlučuje koliko vjerovati inovacijama u odnosu na predikciju. Ako je predikcija nesigurna ($bold(P)^-$ velik) ili su mjerenja precizna ($bold(R)$ malen), $bold(K)$ je velik i filtar slijedi mjerenja. U suprotnom se drži predikcije. Kad bi $bold(P)^-$ bio beskonačan, ažuriranje bi postalo upravo težinski LS iz poglavlja @pog:ls.

Filtar mora odnekud krenuti. Simulator stanje inicijalizira snapshot rješenjem najmanjih kvadrata (pogl. @pog:ls), a početnu nesigurnost postavlja na $bold(P)_0 = 10^6 dot bold(I)$, tj. 1 km po položaju i 1 km/s po brzini. Prva mjerenja zato odmah preuzimaju vodstvo.

#figure(
  image("../slike/08-konvergencija.svg", width: 96%),
  caption: [Pogreška EKF-a po komponentama istok–sjever–gore u prvih 300 s nakon hladnog starta (Zagreb, samo GPS) i interval ±2σ iz kovarijance $bold(P)$.],
) <fig:konv>

@fig:konv prikazuje prvih pet minuta. Nesigurnost se nakon prve epohe svede na nekoliko metara (σ po istoku, sjeveru i visini nakon 1 s: #B.konv_sigma_1s.map(x => br(x)).join(", ") m) i dalje polako pada do #B.konv_sigma_kraj.map(x => br(x, d: 1)).join(", ") m. Pogreška većinu vremena ostaje unutar ±2σ: poslije prvih 30 s to je #B.konv_unutar_2sigma.map(x => br(x, d: 0)).join(" %, ") % epoha po istoku, sjeveru i visini. Za Gaussovu razdiobu očekivalo bi se 95 %.

== Je li filtar iskren? NIS

Filtar ne zna stvarnu pogrešku, ali može provjeriti jesu li inovacije onolike kolike očekuje. Ako su model i šumovi ispravni, normirani kvadrat inovacija

$ "NIS" = bold(y)^T bold(S)^(-1) bold(y) $ <eq:nis>

ima χ² razdiobu s brojem stupnjeva slobode jednakim broju mjerenja, pa je $"NIS"\/n approx 1$. Trajno veći od 1 znači da filtar podcjenjuje šum (preoptimističan je i pogrešno mu se vjeruje). Trajno manji znači da ga precjenjuje (prekonzervativan je i sporije uči). Simulator NIS prikazuje u telemetriji i u donjem doku. U statičnom testu sa @fig:konv srednji NIS/n iznosio je #br(B.konv_nis_sred, d: 2). Malo ispod 1, jer je procesni šum namjerno širok kako bi filtar mogao pratiti i let.

== Cijena kompromisa: procesni šum

Izbor $bold(Q)$ je kompromis. Mali $bold(Q)$ znači da filtar jako vjeruje modelu stalne brzine i snažno usrednjava šum mjerenja, ali ne prati nagle promjene gibanja. Veliki $bold(Q)$ prati svaki manevar, ali propušta više šuma. @fig:q pokazuje taj kompromis na simulatoru. Za statičan prijemnik medijan 3D pogreške raste s #br(qs("staticki", 0.01).med) m pri $bold(Q)$ sto puta manjem od zadanog na #br(qs("staticki", 1.0).med) m pri zadanom. Za prijemnik koji leti po krugu brzinom 60 m/s isti mali $bold(Q)$ daje #br(qs("let", 0.01).med, d: 0) m, jer filtar „” da se prijemnik okreće. Zadana vrijednost u simulatoru daje u letu #br(qs("let", 1.0).med) m.

#figure(
  image("../slike/08-q.svg", width: 90%),
  caption: [Utjecaj procesnog šuma položaja i brzine na pogrešku EKF-a za statičan prijemnik i za let po krugu polumjera 2 km brzinom 60 m/s (Zagreb, samo GPS, dva sjemena × 400 s, bez prvih 60 s). Faktor 1 je vrijednost u simulatoru.],
) <fig:q>

Pravi prijemnici zato često prilagođavaju $bold(Q)$ prema načinu rada (pješak, automobil, zrakoplov) ili ga procjenjuju adaptivno iz inovacija.

== EKF ili snapshot?

Koliko filtar dobiva u odnosu na težinski LS na *istim* mjerenjima? Studija u sandboxu (#kod("sandbox/examples/ekf_vs_wls.json"): pet lokacija × deset sjemena × 180 s, samo GPS) uspoređuje ih u parovima. EKF je imao manju horizontalnu pogrešku p95 u #B.ekfwls_ekf_bolji od #B.ekfwls_parova uparenih runova:

#figure(
  table(
    columns: 5,
    align: (left, right, right, right, right),
    [Lokacija], [EKF horiz. p95], [WLS horiz. p95], [EKF vert. p95], [WLS vert. p95],
    ..B.ekfwls_tablica.pairs().map(((loc, v)) => (
      [#loc], [#br(v.ekf.h_err_p95) m], [#br(v.wls.h_err_p95) m], [#br(v.ekf.v_err_p95) m], [#br(v.wls.v_err_p95) m],
    )).flatten(),
  ),
  caption: [EKF i snapshot WLS na istim mjerenjima (srednja vrijednost preko 10 sjemena). Oba procjenitelja troše oko 2 ms po epohi.],
) <tab:ekfwls>

Filtar dobiva najviše po visini, jer usrednjavanje kroz vrijeme najviše pomaže upravo ondje gdje je geometrija najslabija (pogl. @pog:dop). Detekcija kvarova (pogl. @pog:raim) je za oba procjenitelja jednaka, jer se test integriteta i u EKF-u radi snapshot postupkom nad inovacijama.

#kljucno[
  - Kalmanov filtar je težinski kompromis između predikcije modelom i novog mjerenja. Pojačanje $bold(K)$ određuje taj omjer.
  - $bold(Q)$ i $bold(R)$ su „” filtra. Pogrešno podešeni daju ili šumovito ili tromo rješenje.
  - NIS je unutarnja kontrola: prijemnik bez poznavanja istine može provjeriti je li mu model iskren.
]

#vjezba(vrsta: "racunska", naslov: "Jednodimenzionalni filtar", rjesenje: [
  Uz $P_0 = 100$, $R = 16$ i $Q = 0$: $K_1 = 100\/116 = 0","862$ i $P_1 = 13","8$; $K_2 = 13","8\/29","8 = 0","463$ i $P_2 = 7","41$; $K_3 = 0","317$ i $P_3 = 5","06$. Općenito, uz $Q = 0$ vrijedi $P_k = R \/ (k + R\/P_0)$, pa filtar konvergira prosjeku svih mjerenja i $P_k -> 0$. S $Q = 1$ pojačanje ne pada na nulu: stacionarno $P^- = P + Q$ i $P = P^- R \/ (P^- + R)$ daju $P approx 3","5$, $K approx 0","22$. Filtar tada trajno daje oko 22 % težine novom mjerenju i može pratiti promjene.
])[
  Prijemnik stoji na mjestu, a filtar procjenjuje samo jednu koordinatu. Početna nesigurnost je $P_0 = 100$ m², a svako mjerenje ima $R = 16$ m². Izračunaj $K_k$ i $P_k$ za prva tri mjerenja uz $Q = 0$. Kamo teži $P_k$? Ponovi uz $Q = 1$ m² po koraku i izračunaj stacionarno pojačanje.
]

#vjezba(vrsta: "racunska", naslov: "Prekid signala", rjesenje: [
  Bez mjerenja se primjenjuje samo predikcija. Za statičan model s položajem i brzinom (po jednoj osi) $P_(x x)$ raste zbog $Q_"pos" Delta t$ i zbog $Delta t^2 P_(v v)$. Uz $P_(v v) approx Q_"vel" t$ dobivamo približno $P_(x x)(t) approx P_(x x)(0) + Q_"pos" t + Q_"vel" t^3 \/ 3$. Za $t = 10$ s: $0","5 dot 10 + 1 dot 1000\/3 approx 338$ m², tj. σ oko 18 m. Za 60 s već oko 268 m. Kubni rast dolazi od nesigurnosti brzine. Zato filtri namijenjeni vozilima koriste inercijalne senzore koji brzinu drže točnom i bez satelita.
])[
  Pretpostavi da prijemnik izgubi sve satelite. Koristeći $bold(Q)$ simulatora, procijeni kako raste nesigurnost položaja po jednoj osi nakon 10 s i nakon 60 s, ako je na početku prekida $P_(x x) approx 4$ m² i $P_(v v) approx 0$. Zašto nesigurnost raste brže nego linearno?
]

#vjezba(vrsta: "vodjena", naslov: "Jedan Kalmanov korak", rjesenje: [
  Kartica prikazuje stanje prije predikcije, nakon predikcije i nakon ažuriranja, sve kao pogrešku u ENU u odnosu na istinu i s 1σ. Predikcija pomakne procjenu za brzina × dt i *poveća* σ. Ažuriranje je pomakne prema mjerenjima i *smanji* σ. Doprinosi $K_j y_j$ pojedinih satelita zbrajaju se u ukupnu korekciju. Najveći doprinos obično ima satelit s velikom inovacijom i malom $sigma_j$. Nakon nekoliko koraka predviđena i ažurirana procjena gotovo se poklapaju, jer filtar dobro predviđa statičan prijemnik.
])[
  Pauziraj simulaciju, otvori #ui("Pogled iznutra (matematika epohe)…") i karticu #ui("3. Kalmanov korak"). Usporedi pogrešku i σ prije predikcije, nakon predikcije i nakon ažuriranja. Koji satelit najviše pridonosi korekciji i zašto? Klikni nekoliko puta #ui("Korak +1 s") i prati kako se mijenja veličina korekcije.
]

#vjezba(vrsta: "vodjena", naslov: "Filtar u letu", rjesenje: [
  Uključivanjem #ui("Kinematički (let)") prijemnik se počne gibati. Pogreška u prvim trenucima naraste, jer filtar mora procijeniti novu brzinu. Zatim se vrati na nekoliko metara, ali obično ostaje malo veća nego za statičan prijemnik (usporedi @fig:q). NIS u doku pri naglim promjenama kratko skoči iznad 1: inovacije su veće nego što filtar očekuje. Pri većoj brzini simulacije efekt je izraženiji, jer je korak između epoha dulji.
])[
  Uključi #ui("Kinematički (let)") i prati #ui("Greška"), #ui("Brzina (procjena)") i NIS u donjem doku (#ui("Živi grafovi")). Što se događa neposredno nakon uključivanja? Ponovi uz veću brzinu simulacije. Objasni opažanja pomoću uloge procesnog šuma.
]

#vjezba(vrsta: "istrazivacka", naslov: "EKF protiv WLS-a", rjesenje: [
  Studija daje rezultate iz @tab:ekfwls: EKF je bolji u #B.ekfwls_ekf_bolji od #B.ekfwls_parova uparenih runova. NIS/dof EKF-a je oko 0,75–0,8, a WLS-a (χ²/redundancija) oko 1. Filtar je dakle malo prekonzervativan (široki $bold(Q)$), a snapshot gotovo idealno konzistentan. Za varijantu s kinematikom ova knjiga ne daje broj, jer ga nije izmjerila. Očekivanje je da se prednost filtra smanji, jer se model stalne brzine pri gibanju manje isplati, a s njim i usrednjavanje kroz vrijeme. Svoj rezultat usporedi s @fig:q.
])[
  Pokreni #kod("python sandbox.py run sandbox/examples/ekf_vs_wls.json --workers 4"). Usporedi horizontalnu i vertikalnu pogrešku p95 te NIS po lokacijama. Zatim dodaj kinematiku (#kod("\"kinematic\": {\"speed_mps\": 50}") unutar #kod("world")) i ponovi. Kako se mijenja prednost filtra i zašto?
]
