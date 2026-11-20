#import "../predlozak.typ": *
#let B = json("../skripte/brojke_14.json")
#let c(fault, est, m) = { let v = B.at(fault).at(est).at(m); [#br(v.mean, d: 1) ± #br(v.pm, d: 1)] }

= Istraživački projekti u sandboxu <pog:projekti>


#cilj(
  [postaviti istraživačko pitanje kao uparenu, ponovljivu sandbox studiju],
  [pisati vlastite procjenitelje, napade i metrike kao plugine],
  [čitati rezultate s intervalima pouzdanosti i ne zaključivati previše],
)

Vođene vježbe pokazuju *što* se događa, a računske *zašto*. Istraživački rad postavlja pitanje *koliko*: koliko je jedan algoritam bolji od drugog, je li razlika stvarna ili slučajna, i vrijedi li zaključak na drugim mjestima i u drugim uvjetima. Ovo poglavlje uvodi istraživački sandbox simulatora i predlaže projekte za samostalan rad. Projekti nemaju unaprijed zadan odgovor. Neki od njih nastavljaju se na otvorena pitanja koja je ova knjiga otkrila.

== Kako radi sandbox

Istraživanje se u sandboxu (#kod("sandbox.py")) opisuje jednom JSON specifikacijom. Svaki run je trojka (točka rešetke, lokacija, sjeme). Run je deterministička funkcija, pa se rezultati mogu ponoviti, a ne ovise ni o broju procesa. Ključni dijelovi specifikacije:

- #kod("world"): lokacija ili popis lokacija, trajanje, sustavi, maska, najveći broj satelita, kinematika, teren;
- #kod("seeds"): broj Monte Carlo ponavljanja. Uz #kod("t0_random_s") svako sjeme dobiva i *drugu geometriju* konstelacije, a ne samo drugi šum. Za idealizirani GPS dovoljno je 86 164 s, jedan zvjezdani dan (pogl. @pog:orbite);
- #kod("sweep"): rešetka parametara, npr. veličina napada, $P_"FA"$, maska, sustavi ili estimator;
- #kod("estimators"): jedan ili više procjenitelja. Svi dobivaju *iste* pseudoudaljenosti iste epohe, pa je usporedba uparena;
- #kod("attack"), #kod("raim"), #kod("metrics") i #kod("warmup_s").

Za svaku točku rešetke i procjenitelja sandbox daje srednju vrijednost, medijan, p95 i 95 % interval pouzdanosti srednje vrijednosti preko sjemena (Studentova razdioba). Rezultati se spremaju u #kod("results.json") (uz git commit i inačice za ponovljivost) i CSV datoteke. Isto je dostupno u web-aplikaciji: #ui("Eksperimenti…") → #ui("Sandbox").

```
python sandbox.py list                                   # procjenitelji, napadi, metrike
python sandbox.py validate moja_studija.json             # provjera bez izvođenja
python sandbox.py run moja_studija.json --workers 4 --plot
```

== Vlastiti procjenitelj, napad ili metrika

Sandbox se proširuje *pluginima*: Python modulima koji pri učitavanju registriraju nove procjenitelje (#kod("@register_estimator")), napade (#kod("@register_attack")) i metrike (#kod("@register_metric")), bez diranja koda simulatora. Primjer uz knjigu (#kod("docs/udzbenik/primjeri/plugin_ls.py")) registrira:

- procjenitelj #kod("ls_obicni"): Gauss-Newton bez težina i bez RAIM-a. Klasa ima metodu #kod("solve(signals, t)"), koja vraća položaj (ili #kod("None")) i rječnik s podacima o integritetu, te metodu #kod("estimate()") za odabir satelita;
- metriku #kod("h_err_p99"): funkciju koja iz traga po epohama (polja #kod("t"), #kod("fix"), #kod("err_h"), #kod("err_v"), #kod("hpl"), #kod("detect") …) računa jedan broj.

Studija #kod("docs/udzbenik/primjeri/ls_vs_wls.json") uspoređuje ga s ugrađenim procjeniteljima na istim mjerenjima (6 sjemena × 180 s, samo GPS):

#figure(
  table(
    columns: 5,
    align: (left, right, right, right, right),
    [], [horiz. medijan], [horiz. p95], [horiz. p99], [vert. p95],
    table.cell(colspan: 5, fill: luma(240))[_bez kvara_],
    [obični LS], [#c("0", "ls_obicni", "h_err_median")], [#c("0", "ls_obicni", "h_err_p95")], [#c("0", "ls_obicni", "h_err_p99")], [#c("0", "ls_obicni", "v_err_p95")],
    [WLS + RAIM], [#c("0", "wls", "h_err_median")], [#c("0", "wls", "h_err_p95")], [#c("0", "wls", "h_err_p99")], [#c("0", "wls", "v_err_p95")],
    [EKF + RAIM], [#c("0", "ekf", "h_err_median")], [#c("0", "ekf", "h_err_p95")], [#c("0", "ekf", "h_err_p99")], [#c("0", "ekf", "v_err_p95")],
    table.cell(colspan: 5, fill: luma(240))[_kvar sata od 30 m na jednom satelitu od $t$ = 60 s_],
    [obični LS], [#c("30", "ls_obicni", "h_err_median")], [#c("30", "ls_obicni", "h_err_p95")], [#c("30", "ls_obicni", "h_err_p99")], [#c("30", "ls_obicni", "v_err_p95")],
    [WLS + RAIM], [#c("30", "wls", "h_err_median")], [#c("30", "wls", "h_err_p95")], [#c("30", "wls", "h_err_p99")], [#c("30", "wls", "v_err_p95")],
    [EKF + RAIM], [#c("30", "ekf", "h_err_median")], [#c("30", "ekf", "h_err_p95")], [#c("30", "ekf", "h_err_p99")], [#c("30", "ekf", "v_err_p95")],
  ),
  caption: [Pogreške [m] triju procjenitelja na istim mjerenjima (srednja vrijednost ± poluširina 95 % intervala pouzdanosti preko 6 sjemena).],
) <tab:plugin>

Bez kvara obični i težinski LS gotovo su jednaki (pogl. @pog:ls), a filtar je bolji. S kvarom od 30 m obični LS, koji nema RAIM, gubi najviše. Primijeti i širinu intervala: uz samo šest sjemena razlike između WLS-a i EKF-a uz kvar nisu statistički pouzdane. To je čest zaključak istraživanja, a znači samo: treba više podataka.

== Kako dobro postaviti studiju

+ *Postavi pitanje kao usporedbu.* Ne pitaj „koliko je točan EKF”, nego „za koliko je EKF točniji od WLS-a na istim mjerenjima”.
+ *Variraj geometriju*, a ne samo šum (#kod("t0_random_s")) i, ako je moguće, lokaciju. Zaključak s jednog mjesta i jednog trenutka je anegdota.
+ *Gledaj intervale pouzdanosti.* Razlika koja ne izlazi iz intervala nije dokazana.
+ *Provjeri pretpostavke.* Kao u slučaju granice od deset satelita (pogl. @pog:dop) i RTK eksperimenta (pogl. @pog:rtk), zaključci vrijede samo uz model iz kojeg su izvedeni.
+ *Zabilježi sve*: spec, commit, broj sjemena. Sandbox to čini sam u #kod("results.json").

== Prijedlozi projekata

#vjezba(vrsta: "istrazivacka", naslov: "Koliko satelita u živom prijemniku?", rjesenje: [
  Otvoreno pitanje. Polazište je @fig:studije: s današnjim težinama više satelita pomaže barem do dvadeset. Dobar odgovor uzima u obzir i cijenu: vrijeme po epohi (#kod("runtime_ms")) raste s brojem satelita, a živa simulacija ima budžet od oko 100 ms po epohi. Mogući zaključak je granica koja ovisi o broju uključenih sustava.
])[
  Simulator u rješenje uzima najviše deset satelita (#kod("measurement.MAX_SATS")). Istraži koja bi granica bila najbolja za samo GPS, za dva i za četiri sustava, uz više lokacija i maski. Uzmi u obzir točnost, HPL i vrijeme izvođenja. Predloži novu vrijednost i obrazloži je.
]

#vjezba(vrsta: "istrazivacka", naslov: "Robusni procjenitelj", rjesenje: [
  Otvoreno pitanje. Robusni procjenitelj (npr. Huberova funkcija gubitka kroz iterativno otežavanje) smanjuje utjecaj velikih reziduala bez eksplicitnog isključivanja. Očekuje se da pomaže kod više istodobnih kvarova, gdje RAIM s pretpostavkom jednog kvara ne uspijeva, ali da nema integritetnu granicu (HPL) s jasnom vjerojatnošću.
])[
  Na temelju #kod("plugin_ls.py") napiši procjenitelj s Huberovom funkcijom gubitka (iterativno ponovno otežani LS). Usporedi ga s #kod("wls") i #kod("ekf") uz napad #kod("naive") s 1, 2 i 3 pokvarena satelita. Kada je robusna procjena bolja od RAIM-a, a kada lošija?
]

#vjezba(vrsta: "istrazivacka", naslov: "Prilagodljivi procesni šum", rjesenje: [
  Otvoreno pitanje. Jedan pristup: ako je pomični prosjek NIS/n trajno iznad 1, povećaj $bold(Q)$, a ako je ispod, smanji ga, unutar granica. Uspjeh se mjeri na statičnom i na kinematičkom scenariju istodobno, jer je cilj nadmašiti kompromis s @fig:q.
])[
  @fig:q pokazuje da je najbolji procesni šum za statičan prijemnik loš za let. Napiši procjenitelj koji $bold(Q)$ prilagođava prema NIS-u (pogl. @pog:kalman) i usporedi ga sa zadanim EKF-om na statičnom i kinematičkom scenariju (#kod("world.kinematic.speed_mps")).
]

#vjezba(vrsta: "istrazivacka", naslov: "Djelomično koordinirani napad", rjesenje: [
  Otvoreno pitanje (vidi i vježbu u pogl. @pog:napadi). Očekivani rezultat je prag: dok napadač kontrolira malen dio satelita, rezidual raste i RAIM ga vidi. Iznad nekog udjela napadač može sakriti dio laži u geometriji. Zanimljivo je kako taj prag ovisi o broju sustava.
])[
  Napiši napad (#kod("@register_attack")) koji koordinirano laže samo na udjelu $p$ satelita. Za $p$ = 0,25, 0,5, 0,75 i 1 izmjeri #kod("raim_detections"), #kod("mi_rate") i #kod("final_err"), samo za GPS i za četiri sustava. Koliko satelita napadač mora kontrolirati da ostane neopažen?
]

#vjezba(vrsta: "istrazivacka", naslov: "RTK eksperiment s atmosferom", rjesenje: [
  Otvoreno pitanje i ujedno ispravak simulatora. Offline RTK (#kod("rtk.rtk_solve")) ne uključuje ostatak diferencijalne atmosfere, za razliku od živog RTK-a (pogl. @pog:rtk). Ispravak bi u generiranje faze i koda dodao isti član kao #kod("CarrierPhaseSim.observe") (#kod("ATMO_PPM")), a odluku o fiksiranju doveo na ratio test. Rezultat se provjerava tako da se reproducira @fig:baze.
])[
  Uskladi offline RTK eksperiment s modelom atmosfere iz živog RTK-a. Napiši test koji pokazuje da duljina baze utječe na uspjeh fiksiranja, i usporedi rezultate s @fig:baze.
]

#vjezba(vrsta: "istrazivacka", naslov: "Jednofrekvencijski prijemnik", rjesenje: [
  Otvoreno pitanje. Zahtijeva promjenu mjernog modela: umjesto iono-free kombinacije prijemnik koristi samo L1 i oduzima Klobucharov model. Ostatak ionosfere (stvarna minus modelirana) tada postaje dominantna pogreška i ovisi o dobu dana. Očekuje se da bi klizač doba dana konačno imao vidljiv učinak na točnost (pogl. @pog:pogreske).
])[
  Dodaj u mjerni model mogućnost jednofrekvencijskog prijemnika (samo L1 i Klobucharova korekcija, a stvarna ionosfera malo drukčija od modela, npr. skalirana slučajnim faktorom). Izmjeri točnost kroz dan i usporedi s dvofrekvencijskim prijemnikom.
]

#vjezba(vrsta: "istrazivacka", naslov: "Udžbenik kao istraživanje", rjesenje: [
  Otvoreno pitanje. Svaka brojka u knjizi izračunata je skriptom iz #kod("docs/udzbenik/skripte/"). Promjena modela, primjerice ispravak iz prethodnih projekata, mijenja brojke, a #kod("python docs/udzbenik/build.py --slike") ponovno izgrađuje knjigu s novim vrijednostima. Usporedba starog i novog PDF-a pokazuje što se promijenilo i jesu li zaključci u tekstu i dalje točni.
])[
  Odaberi jednu tvrdnju iz ove knjige koja se oslanja na simulaciju i provjeri je neovisno: drugim sjemenima, drugom lokacijom ili drugom metodom. Ako se ne slaže, pronađi zašto. Rezultat zapiši kao kratko izvješće sa specifikacijom studije i intervalima pouzdanosti.
]
