#import "../predlozak.typ": *
#let B = json("../skripte/brojke_13.json")
#let S = B.spp
#let E = B.eph

= Pravi podaci: RINEX i efemeride <pog:pravi>

Sve dosad radilo je na simuliranim mjerenjima. U ovom poglavlju isti procjenitelj, isti Kalmanov filtar s RAIM-om, dobiva *stvarna* mjerenja geodetskog prijemnika i stvarne navigacijske poruke satelita. Time se zatvara krug: algoritmi iz knjige nisu igračka za simulator, nego rade na podacima iz stvarnog svijeta.

== Format RINEX

Mjerenja GNSS prijemnika razmjenjuju se u formatu *RINEX* (_Receiver Independent Exchange Format_), čitljivom tekstu s fiksnim stupcima. Za pozicioniranje trebaju dvije datoteke:

- *opažanja* (npr. #kod("07590920.05o")): zaglavlje s podacima o stanici (ime, prijemnik, antena, približni položaj #kod("APPROX POSITION XYZ")) i popisom vrsta mjerenja (#kod("C1"), #kod("P2") za kod, #kod("L1"), #kod("L2") za fazu), a zatim epohe s mjerenjima po satelitima;
- *navigacijska poruka* (npr. #kod("07590920.05n")): parametri emitiranih efemerida i sata svakog satelita, a u zaglavlju i koeficijenti Klobucharovog modela ionosfere.

Simulator (#kod("rinex.py")) čita inačice 2 i 3. Uz njega dolazi uzorak iz testnih podataka programa RTKLIB (licenca BSD-2): sat vremena mjerenja geodetske stanice #S.stanica japanske mreže GEONET, prijemnik #S.prijemnik, 2. 4. 2005., #S.epoha epoha u razmaku od 30 s.

== Emitirane efemeride

Navigacijska poruka GPS-a ne sadrži položaj satelita, nego *parametre* iz kojih ga prijemnik računa prema algoritmu iz specifikacije IS-GPS-200 (#kod("ephemeris.sat_position")). To su Keplerovi elementi iz poglavlja @pog:orbite u referentnom trenutku $t_"oe"$, uz:

- korekciju srednjeg gibanja $Delta n$;
- brzinu promjene rektascenzije čvora $dot(Omega)$ i inklinacije $dot(i)$;
- šest harmoničkih korekcija ($C_"uc", C_"us", C_"rc", C_"rs", C_"ic", C_"is"$) argumenta širine, polumjera i inklinacije.

Skup vrijedi oko dva sata oko $t_"oe"$, a prijemnik bira onaj najbliži trenutku mjerenja. Iz istog zapisa dolazi polinom sata satelita ($a_"f0", a_"f1", a_"f2"$), relativistički član @eq:rel i grupno kašnjenje $T_"GD"$ za korisnike koda na L1.

Koliko su emitirane efemeride točne? Uz simulator dolazi i jedna noć *preciznih* orbita službe IGS (format SP3, 15 min, 1. 7. 2010.), izračunatih naknadno iz mreže stotina stanica, s točnošću od nekoliko centimetara. Usporedba s emitiranim efemeridama istog dana (@fig:sp3, #E.n parova za #E.n_sat satelita) daje 3D razliku s medijanom #br(E.med, d: 2) m i 95. percentilom #br(E.p95, d: 2) m. Radijalna komponenta, koja najviše utječe na pseudoudaljenost, ima standardnu devijaciju #br(E.rad_std, d: 2) m. Sat satelita, nakon uklanjanja zajedničkog pomaka, #br(E.clk_std, d: 2) m. To je stvarni izvor pogreške koji simulator modelira Gauss-Markovljevim procesom sa standardnom devijacijom od 1,5 m po osi (pogl. @pog:pogreske).

#figure(
  image("../slike/13-efemeride.svg", width: 94%),
  caption: [Razlika emitiranih efemerida i preciznih IGS orbita (2010-07-01, 00–03 h, svi GPS sateliti). Lijevo: 3D razlika položaja. Desno: razlika sata satelita u metrima, bez zajedničkog pomaka.],
) <fig:sp3>

== Lanac korekcija za jednofrekvencijski SPP

Simulator na stvarnim podacima radi jednofrekvencijsko pozicioniranje iz koda (SPP, _single point positioning_) na C/A kodu L1 (#kod("realdata.py")). Svaka pseudoudaljenost prije predaje filtru dobiva korekcije:

+ *sat satelita*: $+ c Delta t^"sv"$ iz polinoma i relativističkog člana;
+ *grupno kašnjenje*: $- c T_"GD"$;
+ *ionosfera*: Klobucharov model s emitiranim koeficijentima (bez druge frekvencije nema iono-free kombinacije);
+ *troposfera*: Saastamoinenov model sa standardnom atmosferom.

Položaj satelita računa se za *trenutak odašiljanja* (vrijeme prijama minus vrijeme leta minus pogreška sata satelita). Rotaciju Zemlje tijekom leta prijemnik dodaje kroz Sagnacov član, i to samo jednom, jer je dvostruko uračunavanje (u položaju satelita i u modelu) klasična pogreška (pogl. @pog:koordinate). Simulator ima test koji upravo to provjerava.

== Rezultat na pravim podacima

@fig:spp prikazuje pogrešku u odnosu na poznati položaj stanice iz zaglavlja. Svih #S.rijeseno epoha je riješeno, uz masku elevacije od #S.maska° i medijan GDOP-a od #br(S.gdop_med, d: 1):

- horizontalna pogreška: medijan #br(S.ekf.h_med, d: 2) m, p95 #br(S.ekf.h_p95, d: 2) m;
- vertikalna pogreška: medijan #br(S.ekf.v_med, d: 2) m, p95 #br(S.ekf.v_p95, d: 2) m;
- srednji pomak (istok, sjever, gore): #S.ekf.sred.map(x => br(x, d: 2)).join("; ") m;
- RAIM alarma: #S.alarmi.

#figure(
  image("../slike/13-spp.svg", width: 94%),
  caption: [Pogreška SPP rješenja na pravim podacima GEONET stanice 0759 (2005-04-02, sat vremena, 30 s): snapshot LS i EKF s RAIM-om iz simulatora. Krivulje se gotovo poklapaju.],
) <fig:spp>

Dvije stvari zaslužuju pažnju.

*Točnost je bolja nego u simulatoru.* Pola metra vodoravno je mnogo bolje od nekoliko metara koje simulator daje za simulirani dvofrekvencijski prijemnik. Razlog nije u algoritmu, nego u podacima. Ovo je geodetska referentna stanica s kvalitetnom antenom na otvorenom, pa ima vrlo malo multipatha. Kodna mjerenja takvih prijemnika obično su i interno izglađena fazom. Simulator modelira „prosječan” prijemnik, a jednofrekvencijska iono-free usporedba ovdje nije moguća, jer se koristi samo L1 uz Klobuchar.

*EKF i LS daju isto.* Rješenja se razlikuju najviše #br(B.ekf_ls_max_razlika_mm, d: 0) mm. Uz razmak epoha od 30 s i procesni šum podešen za žive simulacije od 1 s, predikcija filtra nakon 30 s praktički ne nosi informaciju, pa ažuriranje ovisi samo o mjerenjima (pogl. @pog:kalman). S tisuću puta manjim procesnim šumom vertikalni medijan pada na #br(B.mali_q.v_med, d: 2) m. Filtar mora biti podešen za podatke koje obrađuje.

#kljucno[
  - Algoritmi iz ove knjige rade na stvarnim mjerenjima bez izmjene. Mijenja se samo izvor pseudoudaljenosti.
  - Emitirane efemeride griješe 1–4 m u položaju satelita, a precizne IGS orbite su točne na centimetre.
  - Parametri filtra ovise o podacima: isti filtar se na 1 s i na 30 s ponaša različito.
]

#vjezba(vrsta: "vodjena", naslov: "Pravi podaci u aplikaciji", rjesenje: [
  Kartica obrađuje priloženi uzorak. Uz zadanu masku i EKF #ui("Horiz. medijan") je oko 0,4 m, a #ui("Vert. 95%") oko 2 m, kao u ovom poglavlju. Graf #ui("Greška pozicije vs. referenca (m)") pokazuje mirnu horizontalnu i nemirniju vertikalnu pogrešku. Uz #ui("LS") rezultati su praktički isti (objašnjenje je u tekstu). Uz masku od 25° satelita je manje i geometrija je lošija: horizontalni medijan raste na #br(B.maska25.h_med, d: 2) m, vertikalni na #br(B.maska25.v_med, d: 2) m, a vertikalni p95 na #br(B.maska25.v_p95, d: 0) m.
])[
  Otvori #ui("Eksperimenti…") i karticu #ui("Pravi podaci"). Pokreni obradu s #ui("EKF + RAIM"), a zatim s #ui("LS"). Usporedi #ui("Horiz. medijan"), #ui("Horiz. 95%"), #ui("Vert. medijan") i #ui("Srednji pomak E/N/U"). Ponovi uz masku elevacije od 25°.
]

#vjezba(vrsta: "racunska", naslov: "Zaglavlje RINEX-a", rjesenje: [
  Redak #kod("APPROX POSITION XYZ") sadrži tri broja u metrima (ECEF). Pretvorba (pogl. @pog:koordinate) daje položaj u Japanu: #br(B.stanica_lla.at(0), d: 2)° N, #br(B.stanica_lla.at(1), d: 2)° E i visinu od #br(B.stanica_lla.at(2), d: 0) m iznad elipsoida. Ostali retci zaglavlja navode prijemnik (#S.prijemnik), vrstu antene, interval (30 s) i vrste mjerenja (#kod("L1 L2 C1 P2") …).
])[
  Otvori datoteku #kod("tests/data/07590920.05o") u uređivaču teksta. Pronađi #kod("APPROX POSITION XYZ"), pretvori ga u geodetsku širinu, dužinu i visinu i provjeri gdje je stanica. Koje vrste mjerenja datoteka sadrži i u kojem intervalu?
]

#vjezba(vrsta: "racunska", naslov: "Emitirano naspram preciznog", rjesenje: [
  Petlja iz #kod("tests/test_realdata.py") (funkcija koja koristi #kod("read_sp3")) daje medijan oko #br(E.med, d: 1) m i maksimum oko #br(E.max, d: 1) m. Rastav na komponente pokazuje da je radijalna pogreška najmanja (standardna devijacija #br(E.rad_std, d: 2) m), poprečna #br(E.pop_std, d: 2) m, a uzduž putanje najveća (#br(E.uz_std, d: 2) m). Kontrolni segment najbolje određuje visinu, a najlošije položaj satelita uzduž orbite. Za korisnika na Zemlji radijalna komponenta je gotovo u smjeru linije pogleda, pa je pogreška pseudoudaljenosti manja od 3D pogreške položaja.
])[
  Pomoću #kod("rinex.read_nav"), #kod("rinex.read_sp3"), #kod("ephemeris.select_ephemeris") i #kod("ephemeris.sat_position") izračunaj razliku emitiranih i preciznih orbita iz #kod("tests/data/brdc1820_trim.10n") i #kod("igs15904_trim.sp3"). Rastavi je na radijalnu komponentu, komponentu uzduž putanje i poprečnu komponentu. Koja je najveća? Zašto je za korisnika najvažnija radijalna?
]

#vjezba(vrsta: "istrazivacka", naslov: "Tvoja stanica", rjesenje: [
  Rezultat ovisi o odabranoj stanici i danu. Za stanicu na otvorenom s geodetskom antenom očekuje se horizontalna pogreška SPP-a reda metra. Za prijemnik u gradu ili s jeftinom antenom više metara, s izraženijim repovima (p95). Ako RAIM alarmira, pogledaj u kojim epohama i kojim satelitima. To su često niski sateliti s multipathom ili skokovi sata prijemnika.
])[
  Pribavi RINEX opažanja i navigacijsku datoteku za jedan dan neke stanice (npr. iz arhive službe IGS ili nacionalne mreže referentnih stanica). Pokreni #kod("python realdata.py <opažanja> <navigacija> --plot rezultat.png") i usporedi rezultat s uzorkom iz ovog poglavlja. Pokušaj i #kod("--solver ls") te različite maske (#kod("--mask")).
]
