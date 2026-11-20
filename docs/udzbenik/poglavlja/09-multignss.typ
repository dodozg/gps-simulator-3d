#import "../predlozak.typ": *
#let B = json("../skripte/brojke_09.json")
#let S = B.studija
#let tocka(ime, x) = S.at(ime).filter(p => p.x == x).first()
#let mm(ime, x, m, d: 1, k: 1) = { let v = tocka(ime, x).at(m).mean; if v == none [—] else [#br(v * k, d: d)] }

= Više sustava: multi-GNSS <pog:multignss>


#cilj(
  [zašto svaki sustav donosi vlastitu nepoznanicu (ISB)],
  [kako filtar procjenjuje ISB i što on zapravo upija],
  [gdje je korist više sustava najveća: dostupnost i integritet pod zaklonjenim nebom],
)

Do sada je prijemnik koristio uglavnom samo GPS. Moderni prijemnici prate sva četiri globalna sustava istodobno i tako umjesto sedam ili osam satelita vide tridesetak (pogl. @pog:gnss). Ovo poglavlje pokazuje što to donosi, koju novu nepoznanicu uvodi i gdje je korist najveća.

== Svaki sustav ima svoj sat

GPS, Galileo, GLONASS i BeiDou održavaju vlastite vremenske skale, a njihove međusobne razlike nisu nula. Uz to, signali različitih sustava različito kasne kroz elektroniku prijemnika. Za prijemnik je posljedica ista: pseudoudaljenosti svakog sustava imaju vlastiti stalni pomak. Jednadžba @eq:pr zato postaje

$ rho_i = norm(bold(s)_i - bold(x)) + b + "ISB"_(s(i)) + epsilon_i , $ <eq:isb>

gdje je $"ISB"_s$ (_inter-system bias_) pomak sustava $s$ u odnosu na GPS (za GPS $"ISB" = 0$). Svaki dodatni sustav donosi jednu nepoznanicu više. Prvi satelit novog sustava zato se „potroši” na procjenu njegovog ISB-a, a tek ostali pridonose položaju. Najmanji broj satelita za rješenje s $k$ sustava je $3 + k$.

U simulatoru su istiniti ISB-ovi #B.isb_istina.GAL m za Galileo, #B.isb_istina.GLO m za GLONASS i #B.isb_istina.BDS m za BeiDou. Ubrizgavaju se u mjerenja, a Kalmanov filtar ih procjenjuje kao tri dodatna stanja (pogl. @pog:kalman). @fig:isb pokazuje kako procjene konvergiraju. Nakon deset minuta filtar procjenjuje #br(B.isb_kraj.GAL) m, #br(B.isb_kraj.GLO) m i #br(B.isb_kraj.BDS) m, uz σ od oko #br(B.isb_sigma_kraj.GAL, d: 1) m.

#figure(
  image("../slike/09-isb.svg", width: 90%),
  caption: [Procjena ISB-a u EKF-u od hladnog starta (Zagreb, četiri sustava). Iscrtkano: istinite vrijednosti. Vrpca: ±2σ iz kovarijance filtra.],
) <fig:isb>

Procjene ne stoje točno na istini, nego do 1–2 m pokraj nje, i to izvan intervala ±2σ. Razlog je poučan. ISB je zajednički svim satelitima jednog sustava, pa upija i *zajednički dio* drugih sporo promjenjivih pogrešaka tih satelita, ponajprije pogreške efemerida (pogl. @pog:pogreske). Filtar ne može razlikovati „sat sustava kasni 1,5 m” od „svi sateliti sustava su prosječno 1,5 m dalje nego što kažu efemeride”. Za položaj to nije štetno, jer se oba učinka u modelu poništavaju. Ali ISB iz navigacijskog filtra nije čisto mjerenje razlike vremenskih skala.

#napomena(naslov: "Što simulator pojednostavljuje")[
  U stvarnosti se sustavi razlikuju i signalima. Galileo E1 koristi modulaciju BOC(1,1), GLONASS razdvaja satelite frekvencijom (FDMA), a BeiDou B1I ima drukčiju brzinu koda. Simulator svim sustavima daje kod nalik GPS-ovom C/A, a međusobno ometanje računa samo unutar istog sustava, kao zamjenu za stvarno razdvajanje frekvencijom ili modulacijom. Za navigacijski dio, koji je tema ovog poglavlja, ta razlika nije bitna.
]

== Dobitak: geometrija i dostupnost

Više satelita znači bolju geometriju (pogl. @pog:dop) i više redundancije za provjeru integriteta (pogl. @pog:raim). Najvažnija je ipak *dostupnost*: kad je dio neba zaklonjen, u urbanom kanjonu, šumi ili dolini, jedan sustav brzo ostane bez dovoljno satelita.

Studija u sandboxu (#kod("sandbox/examples/multignss_mask.json"), Zagreb, 8 sjemena × 60 s, najviše 16 satelita u rješenju, HAL = 100 m) mijenja elevacijsku masku kao zamjenu za zaklonjenost neba (@fig:mgstudija):

- *Samo GPS*: uz masku 5° u rješenju je prosječno #mm("GPS", 5, "n_sats_mean") satelita i medijan HPL-a #mm("GPS", 5, "hpl_median", d: 0) m. Uz masku 20° ostaje #mm("GPS", 20, "n_sats_mean") satelita, a HPL ≤ 100 m vrijedi u samo #mm("GPS", 20, "integrity_availability", d: 0, k: 100) % epoha. Uz 40° fix postoji u #mm("GPS", 40, "availability", d: 0, k: 100) % epoha, a horizontalna pogreška p95 je #mm("GPS", 40, "h_err_p95", d: 0) m.
- *GPS + Galileo*: integritet ostaje potpuno dostupan do maske 25° (HPL #mm("GPS+Galileo", 25, "hpl_median", d: 0) m), a pri 30° pada na #mm("GPS+Galileo", 30, "integrity_availability", d: 0, k: 100) %.
- *Četiri sustava*: i uz masku 40° prijemnik ima #mm("četiri sustava", 40, "n_sats_mean") satelita, HPL #mm("četiri sustava", 40, "hpl_median", d: 0) m i dostupnost integriteta #mm("četiri sustava", 40, "integrity_availability", d: 0, k: 100) %. Horizontalna pogreška p95 je u cijelom rasponu između #mm("četiri sustava", 20, "h_err_p95") m i #mm("četiri sustava", 35, "h_err_p95") m.

#figure(
  image("../slike/09-studija.svg", width: 100%),
  caption: [Multi-GNSS i elevacijska maska (sandbox, EKF, srednje vrijednosti preko 8 sjemena). Lijevo: broj satelita u rješenju (najviše 16). Sredina: medijan zaštitne granice HPL (log-mjerilo). Desno: udio epoha u kojima je HPL ≤ 100 m.],
) <fig:mgstudija>

Jedna pojedinost s @fig:mgstudija zaslužuje pažnju. S četiri sustava HPL je uz masku 5° *veći* (#mm("četiri sustava", 5, "hpl_median", d: 0) m) nego uz masku od 15° do 25°. Broj satelita je u svim tim točkama isti (16, granica odabira). Razlika je u tome koje satelite odabir uzme: pri niskoj maski među njima je više niskih, šumovitijih satelita, pa im prijemnik pridružuje veće $sigma$ i zaštitna granica raste. Više kandidata ne znači nužno bolji izbor ako se bira samo po geometriji. Istraživačka vježba na kraju poglavlja traži da to provjeriš.

#kljucno[
  - Svaki dodatni sustav donosi jednu nepoznanicu (ISB) i mnogo satelita. Isplati se čim sustav ima barem dva satelita u rješenju.
  - Najveća korist multi-GNSS-a nije točnost na otvorenom, nego dostupnost i integritet kad je nebo zaklonjeno.
  - ISB iz navigacijskog filtra upija i zajedničke pogreške satelita svog sustava.
]

#vjezba(vrsta: "racunska", naslov: "Brojanje nepoznanica", rjesenje: [
  (a) GPS + Galileo: 3 + 2 = 5 nepoznanica (tri koordinate, sat i ISB Galilea). Ako su u rješenju samo GPS sateliti, dovoljna su četiri. Čim je u rješenju barem jedan Galileo satelit, treba ih ukupno barem pet. (b) S četiri sustava 7 nepoznanica. Sa 6 GPS i po 1 satelitom ostalih sustava redundancija je $9 - 7 = 2$, a ne 5: svaki usamljeni satelit „pojede” vlastiti ISB i ne pridonosi ni položaju ni provjeri. (c) Kad je ISB poznat (npr. emitiran u poruci ili kalibriran), nepoznanica nestaje i usamljeni satelit postaje koristan. Galileo u navigacijskoj poruci emitira razliku GPS–Galileo vremena (GGTO).
])[
  (a) Koliko nepoznanica ima rješenje s GPS-om i Galileom? Koliko je najmanje satelita potrebno? (b) Prijemnik vidi 6 GPS satelita i po jedan satelit Galilea, GLONASS-a i BeiDoua. Kolika je redundancija? Koliko bi bila da su sva četiri sustava jedan? (c) Kako bi se situacija promijenila kad bi ISB bio unaprijed poznat?
]

#vjezba(vrsta: "vodjena", naslov: "ISB uživo", rjesenje: [
  U stručnom načinu telemetrija za svaki uključeni sustav prikazuje #ui("ISB (procjena)") i #ui("ISB (istina)"). Nakon uključivanja sustava procjena kreće od nule i u desetak sekundi dođe blizu istine, a zatim se ustali unutar metra ili dva. Kad se sustav isključi, njegov ISB se više ne ažurira. Kad se ponovno uključi, filtar ga nastavlja od zadnje vrijednosti. ISB je gotovo stalan ($bold(Q)_"ISB"$ = 0,01 m²/s), pa se ne „zaboravlja” brzo.
])[
  Uključi #ui("Stručnjak"), sve sustave i pokreni simulaciju. U telemetriji pronađi ISB-ove i usporedi procjenu s istinom. Isključi Galileo na minutu simulacije pa ga ponovno uključi. Što se događa s procjenom njegovog ISB-a?
]

#vjezba(vrsta: "vodjena", naslov: "Eksperiment Multi-GNSS", rjesenje: [
  Graf dostupnosti pokazuje da broj satelita samog GPS-a s porastom maske brzo pada ispod potrebnog minimuma, a sa svim sustavima ostaje dovoljno satelita i pri visokim maskama. Tablica ISB-ova pokazuje procjene blizu istine, uz odstupanja od nekoliko metara jer je to snapshot rješenje jedne epohe. PDOP sa svim sustavima je osjetno manji nego samo s GPS-om.
])[
  Otvori #ui("Eksperimenti…") i karticu #ui("Multi-GNSS"). Pokreni eksperiment za Zagreb uz masku 10° i 30°. Usporedi #ui("GPS sateliti") i #ui("Svi sustavi"), graf #ui("Dostupnost (broj satelita po maski)") i tablicu ISB-ova.
]

#vjezba(vrsta: "istrazivacka", naslov: "Zašto je HPL uz nisku masku veći?", rjesenje: [
  Ova knjiga to *objašnjava*, ali ne *dokazuje*. Dokaz je tvoj zadatak. Prijedlog: u kopiji speca #kod("multignss_mask.json") za četiri sustava dodaj sweep po #kod("max_sats") (npr. 10, 16, 24) i metriku #kod("n_sats_mean"). Ako je objašnjenje točno, s više dopuštenih satelita HPL uz nisku masku trebao bi pasti, jer se uz geometrijski najbolje mogu zadržati i mirniji visoki sateliti. Druga provjera je usporediti medijan elevacije odabranih satelita, što zahtijeva vlastitu metriku (#kod("@register_metric"), pogl. @pog:projekti).
])[
  Na @fig:mgstudija HPL sa četiri sustava ne pada monotono s nižom maskom. Postavi hipotezu i osmisli sandbox studiju kojom je provjeravaš. Odvrti je i zaključi.
]
