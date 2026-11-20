#import "../predlozak.typ": *
#let B = json("../skripte/brojke_04.json")

= Signal: kod, korelacija i C/N0 <pog:signal>


#cilj(
  [kako su građeni C/A kod i Gold kodovi i zašto se sateliti ne miješaju],
  [kako petlja koda mjeri kašnjenje i odakle joj šum],
  [izračunati C/N0 iz link budgeta i šum koda iz C/N0],
  [što su Doppler, međusobno ometanje i gubitak zabrave],
)

Pseudoudaljenost nije izmjerena ravnalom, nego korelatorom. Prijemnik pomiče lokalnu kopiju koda satelita dok se ne poravna s primljenim signalom, a pomak u trenutku poravnanja je vrijeme leta. Ovo poglavlje objašnjava kako je signal građen, kako se iz šuma izvlači mjerenje točno na metar i o čemu ovisi koliko je to mjerenje šumovito.

== Građa signala

GPS satelit emitira na dvije glavne frekvencije: *L1* = 1575,42 MHz i *L2* = 1227,60 MHz. Nosilac je fazno moduliran (BPSK) *kodom* i *navigacijskom porukom*:

- *C/A kod* (_coarse/acquisition_) je niz od 1023 *čipa* vrijednosti ±1, koji se ponavlja svake milisekunde (brzina 1,023 Mčip/s). Jedan čip traje oko 1 µs, što odgovara #br(B.cip_m) m.
- *Navigacijska poruka* brzinom 50 bit/s nosi efemeride, korekcije sata i almanah.

Svaki satelit ima vlastiti kod. Svi emitiraju na istoj frekvenciji, a prijemnik ih razdvaja upravo po kodu (CDMA). To funkcionira samo ako kodovi imaju posebna korelacijska svojstva.

== Gold kodovi

C/A kodovi su *Gold kodovi*: zbroj modulo 2 dvaju 10-bitnih pomačnih registara s povratnom vezom (LFSR) $G_1 = 1 + x^3 + x^10$ i $G_2 = 1 + x^2 + x^3 + x^6 + x^8 + x^9 + x^10$, pri čemu je $G_2$ zakašnjen za broj čipova svojstven satelitu. Simulator generira upravo te kodove (#kod("signal_processing.gold_code")).

Ključna su dva svojstva (@fig:gold). *Autokorelacija* koda sa samim sobom ima oštar vrh od #B.auto_vrh na nultom pomaku, a za sve ostale pomake poprima samo vrijednosti iz skupa {#B.auto_ostalo.map(str).join(", ")}. *Međukorelacija* dvaju različitih Gold kodova poprima također samo te tri vrijednosti. Za dva slučajna ±1 niza iste duljine međukorelacija nije omeđena: u našem primjeru doseže #B.slucajni_max. Ograničenost na 65 od 1023 (−24 dB) znači da se slabiji satelit ne utopi u jačem, dok im razlika snaga nije prevelika.

#figure(
  image("../slike/04-gold.svg", width: 100%),
  caption: [Lijevo: autokorelacija C/A Gold koda iz simulatora. Desno: međukorelacija dvaju Gold kodova (narančasto) poprima samo vrijednosti −65, −1 i 63 (točkaste linije), za razliku od dva slučajna niza (sivo).],
) <fig:gold>

== Korelacija i praćenje koda

Zamislimo idealan signal bez šuma. Za pravokutne čipove korelacija primljenog i lokalnog koda u ovisnosti o pogrešci kašnjenja $tau$ (u čipovima) je trokut $R(tau) = 1 - |tau|$ za $|tau| < 1$, a nula izvan toga. Prijemnik u fazi *akvizicije* grubo pretraži sve pomake koda i Dopplerove pomake dok ne nađe vrh. Zatim prelazi u *praćenje*.

Praćenje koda radi petlja DLL (_delay lock loop_). Uz *točni* (P) korelator računa još *rani* (E) i *kasni* (L), pomaknute za $plus.minus d\/2$ čipa. Razlika njihovih snaga, *diskriminator*,

$ D(tau) = |R(tau + d\/2)|^2 - |R(tau - d\/2)|^2 $ <eq:diskriminator>

nula je kad je lokalni kod točno poravnan i mijenja predznak oko nule (@fig:dll). Petlja pomiče lokalni kod tako da $D$ drži na nuli. Izlaz petlje je kašnjenje koda, a iz njega pseudoudaljenost. Simulator koristi $d = 0","5$ čipa i šumnu širinu petlje $B_L = 2$ Hz.

#figure(
  image("../slike/04-dll.svg", width: 96%),
  caption: [Lijevo: korelacijska funkcija C/A koda i položaj ranog i kasnog korelatora. Desno: diskriminator rani-minus-kasni. Linearno područje oko nule je ono u kojem petlja radi.],
) <fig:dll>

Sve što pomakne nul-prijelaz diskriminatora stvara *pristranost* mjerenja. Multipath (zakašnjeli odraz) iskrivi korelacijski trokut. Međukorelacija s jačim satelitom doda mali, Gold-kodom omeđen doprinos. Simulator računa obje pristranosti iz geometrije odraza i stvarnih Gold vrijednosti.

== Snaga signala: C/N0

Kvaliteta praćenja ovisi o omjeru snage nosioca i spektralne gustoće šuma, *C/N0* (dB-Hz). Simulator ga računa iz *link budgeta* (#kod("signal_model.cn0_dbhz")):

- primljena snaga u izotropnu antenu na 20 200 km: −155,5 dBW na L1 i −158,5 dBW na L2;
- slabljenje s udaljenošću ($1\/d^2$) i dobitak oblikovanog snopa satelitske antene prema rubu Zemlje (+2 dB);
- gušenje u atmosferi i dijagram antene prijemnika (+3 dBic u zenitu, oko −7 dBic na 5°);
- šumni pod $N_0 = k(T_"ant" + T_0(F - 1))$ = #br(B.N0_dbw_hz) dBW/Hz (uz šumni faktor 2 dB) i 2 dB implementacijskih gubitaka.

Rezultat (@fig:cn0) je #br(B.gps_l1_zenit) dB-Hz za GPS L1 u zenitu, #br(B.gps_l1_30) dB-Hz na 30° i #br(B.gps_l1_5) dB-Hz na 5°. Primljeni signal je oko 20 dB *ispod* toplinskog šuma u pojasu od 2 MHz. Tek korelacija s poznatim kodom preko 1023 čipa i integracija kroz 20 ms izvuku ga iznad šuma.

#figure(
  image("../slike/04-cn0.svg", width: 88%),
  caption: [Nominalni C/N0 iz link budgeta simulatora u ovisnosti o elevaciji. Galileo je zbog veće udaljenosti malo slabiji, a GLONASS jači. Ispod 28 dB-Hz prijemnik gubi zabravu.],
) <fig:cn0>

== Šum koda

Toplinski šum na diskriminatoru prelazi u slučajnu pogrešku kašnjenja. Za nekoherentni rani-minus-kasni diskriminator vrijedi (Betz i Kolodziejski)

$ sigma_tau^2 = (B_L d) / (2 "C/N0") (1 + 2 / ((2 - d) T "C/N0")) quad ["čip"^2] , $ <eq:dllsigma>

uz C/N0 u linearnim jedinicama (Hz) i vrijeme koherentne integracije $T$ = 20 ms. Za L1 to daje #br(B.sigma_l1_49, d: 2) m pri 49 dB-Hz, #br(B.sigma_l1_39, d: 2) m pri 39 dB-Hz i već #br(B.sigma_l1_30, d: 2) m pri 30 dB-Hz (@fig:sumkoda). Uži $B_L$ ili manji razmak $d$ smanjuju šum, ali petlja tada sporije reagira, odnosno ima uži linearni raspon.

#figure(
  image("../slike/04-sum-koda.svg", width: 86%),
  caption: [Standardna devijacija šuma koda prema @eq:dllsigma za L1 i za iono-free kombinaciju L1/L2 (pogl. @pog:pogreske), u ovisnosti o C/N0.],
) <fig:sumkoda>

Simulator uz svako mjerenje predaje i tu procjenu ($sigma_"kod"$ u @eq:sigma, pogl. @pog:ls), kao što pravi prijemnici daju svoju procjenu točnosti pseudoudaljenosti. Navigacijski filtar zato slabim satelitima automatski daje manju težinu.

== Doppler, koherentna integracija i međusobno ometanje

Satelit se prijemniku približava ili udaljava brzinom do oko 800 m/s, pa je primljena frekvencija pomaknuta Dopplerovim efektom. Za idealizirani GPS iz Zagreba najveći Doppler na L1 bio je #br(B.doppler_max_hz, d: 0) Hz. Prijemnik ga mora pratiti petljom nosioca. Doppler je ujedno koristan: smetnja koja je od signala pomaknuta za $Delta f$ prolazi koherentnu integraciju trajanja $T$ prigušena faktorom $|"sinc"(pi Delta f T)|$. Već za 25 Hz to je #br(B.koh_25hz, d: 2), a na višekratnicima od 50 Hz nula.

C/A kod se ponavlja svake milisekunde, pa mu je spektar linijski, s razmakom 1 kHz. Međukorelacija dvaju satelita zato kroz integraciju prolazi ovisno o tome koliko je njihova razlika Dopplera blizu višekratnika od 1 kHz. Prosječno to daje poznati koeficijent od #br(B.mai_sred_db) dB/Hz. Za satelite iste snage gubitak C/N0 zbog ostalih satelita (MAI, _multiple access interference_) je obično ispod pola decibela, a povremeno, kad se Doppleri dvaju satelita poklope, i nekoliko decibela. Kad je jedan satelit znatno jači, primjerice lažni odašiljač (pogl. @pog:napadi), slabijima povremeno sruši C/N0 za 10 i više dB. To je poznati problem *near-far*.

== Gubitak zabrave i ometanje

Kad efektivni C/N0 padne ispod oko 28 dB-Hz, petlje (uz $T$ = 20 ms) više ne mogu pratiti signal i prijemnik ga *gubi*. Širokopojasni ometač s omjerom snage ometanja i šuma $J\/N$ podiže šumni pod:

$ ("C/N0")_"eff" = "C/N0" - 10 log_10 (1 + J\/N) . $ <eq:jam>

Ometač od 10 dB iznad šuma tako smanjuje C/N0 svih satelita za #br(B.jam_10db) dB. Sateliti nisko nad horizontom, koji su ionako najslabiji, prvi gube zabravu, a preživjeli postaju šumovitiji. Simulator upravo tako modelira ometanje (pogl. @pog:napadi).

#kljucno[
  - Pseudoudaljenost je izlaz petlje koda. Njezin šum određuje C/N0, a pristranost sve što iskrivi korelacijski trokut.
  - C/N0 je najvažniji pokazatelj kvalitete pojedinog mjerenja. Dobri prijemnici njime otežavaju mjerenja.
  - Gold kodovi i koherentna integracija razdvajaju satelite na istoj frekvenciji, ali samo dok im razlika snaga nije prevelika.
]

#vjezba(vrsta: "racunska", naslov: "Gold kod u Pythonu", rjesenje: [
  Iz korijena repozitorija: #kod("import signal_processing as sp; a = sp.gold_code(5)"). Kružna korelacija preko FFT-a (#kod("np.fft.ifft(np.fft.fft(a) * np.conj(np.fft.fft(b))).real")) daje za $a$ sa samim sobom 1023 na pomaku 0, a za ostale pomake samo −65, −1 i 63. Za $a$ i drugi kod rezultat poprima isključivo vrijednosti iz istog skupa. Za slučajne nizove dobiju se vrijednosti do oko ±100, ovisno o sjemenu (u primjeru sa @fig:gold[slike] #B.slucajni_max). Gold kodovi garantiraju gornju granicu, a slučajni nizovi ne.
])[
  Pomoću funkcije #kod("signal_processing.gold_code(shift)") generiraj dva C/A koda i izračunaj njihovu kružnu autokorelaciju i međukorelaciju za sve pomake. Koje vrijednosti poprimaju? Ponovi s dva slučajna ±1 niza duljine 1023 i usporedi najveću međukorelaciju.
]

#vjezba(vrsta: "racunska", naslov: "Link budget", rjesenje: [
  $"C/N0" = P_"rx" + G_"ant" - N_0 - L_"impl" = -155","5 + 3 - (-203","8) - 2 approx 49","3$ dB-Hz u zenitu. Na 5° udaljenost je oko 25 250 km, pa slabljenje iznosi $20 log_10(25 space 250 \/ 20 space 200) approx 1","9$ dB. Antena daje −7 dBic umjesto +3, a snop satelita +2 dB, pa je $"C/N0" approx 49","3 - 1","9 - 10 + 2 - 0","4 approx 39$ dB-Hz (u simulatoru #br(B.gps_l1_5) dB-Hz). Pomoć: 0,4 dB je atmosfersko gušenje $0","035 \/ sin 5°$.
])[
  Iz podataka u odjeljku o C/N0 izračunaj C/N0 GPS signala na L1 u zenitu i na elevaciji 5°. Udaljenost na 5° izračunao si u vježbi iz poglavlja 1. Koji član link budgeta najviše pridonosi razlici?
]

#vjezba(vrsta: "racunska", naslov: "Šum koda", rjesenje: [
  Uz C/N0 = 49 dB-Hz $= 7","94 dot 10^4$ Hz: $sigma_tau^2 = 2 dot 0","5 \/ (2 dot 7","94 dot 10^4) dot (1 + 2 \/ (1","5 dot 0","02 dot 7","94 dot 10^4)) = 6","30 dot 10^(-6) dot 1","0008$, pa je $sigma_tau = 2","51 dot 10^(-3)$ čipa $approx$ #br(B.sigma_l1_49, d: 2) m. Pad na 39 dB-Hz (10 dB) povećava $sigma$ približno $sqrt(10) approx 3","2$ puta, na #br(B.sigma_l1_39, d: 2) m. Drugi član u zagradi (gubitak kvadriranja) postaje važan tek blizu praga, zato je krivulja na @fig:sumkoda[slici] u log-mjerilu gotovo pravac.
])[
  Prema @eq:dllsigma izračunaj $sigma$ šuma koda u metrima za C/N0 = 49 dB-Hz i 39 dB-Hz ($B_L$ = 2 Hz, $d$ = 0,5, $T$ = 20 ms). Koliko puta naraste $sigma$ kad C/N0 padne za 10 dB? Zašto?
]

#vjezba(vrsta: "vodjena", naslov: "C/N0 i elevacija uživo", rjesenje: [
  C/N0 u tablici raste s elevacijom, od oko 39 dB-Hz kod satelita blizu 5° do oko 49 dB-Hz kod satelita blizu zenita. Kad uključiš Galileo, njegovi sateliti na sličnoj elevaciji imaju oko 1 dB niži C/N0 (dalje su), a GLONASS-ovi malo viši. Isti satelit kroz vrijeme mijenja C/N0 kako mu se mijenja elevacija. Male nagle promjene (do par dB) potječu od međusobnog ometanja kad se Doppleri dvaju satelita poklope.
])[
  U tablici #ui("Sateliti u vidokrugu") usporedi stupce #ui("Elev") i #ui("C/N0") za sve satelite. Nacrtaj na papiru C/N0 u ovisnosti o elevaciji i usporedi sa @fig:cn0[slikom]. Uključi Galileo i GLONASS. Razlikuju li se njihovi sateliti na sličnoj elevaciji?
]

#vjezba(vrsta: "vodjena", naslov: "Near-far: jedan preglasan satelit", rjesenje: [
  Povećanje snage odabranog satelita za 25 dB ne mijenja njegov vlastiti položaj u rješenju, ali ostalim satelitima istog sustava povremeno spusti C/N0 za nekoliko do dvadesetak decibela: kad im se relativni Doppler s jakim satelitom poklopi s linijom spektra C/A koda, njegova međukorelacija prođe integraciju. Najslabiji sateliti tada mogu izgubiti zabravu i ispasti iz tablice. Sateliti drugih sustava nisu pogođeni, jer simulator međusobno ometanje računa samo unutar sustava (u stvarnosti sustave razdvajaju frekvencija ili modulacija).
])[
  Otvori editor jednog GPS satelita visoko na nebu i postavi #ui("Snaga signala [dB]") na +25. Prati C/N0 ostalih GPS satelita nekoliko minuta simulacije. Što se događa? Je li pogođen i neki Galileo satelit? Vrati snagu na 0 gumbom #ui("Zdrav (poništi kvarove)").
]
