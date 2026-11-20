#import "../predlozak.typ": *
#let B = json("../skripte/brojke_11.json")
#let T3 = B.tijek.tri
#let TG = B.tijek.gps
#let bz(km) = B.baze.filter(p => p.km == km).first()

= Fazna mjerenja i RTK <pog:rtk>


#cilj(
  [zašto je faza nosioca precizna, ali dvosmislena],
  [kako dvostruke razlike poništavaju satove i atmosferu],
  [kako se cjelobrojne neodređenosti fiksiraju metodom LAMBDA i kada im se smije vjerovati],
  [zašto duljina baze ograničava RTK],
)

Sve dosad radilo je s kodom: pseudoudaljenost s šumom od metra i točnošću položaja od nekoliko metara. Geodezija, poljoprivreda i strojevi koji se sami voze trebaju centimetre. Do njih se dolazi mjerenjem *faze nosioca*, a ne koda, i to relativno u odnosu na obližnju referentnu stanicu. Ovo poglavlje objašnjava RTK (_real-time kinematic_) i najvažniji pojam precizne navigacije: cjelobrojnu neodređenost.

== Faza nosioca

Valna duljina nosioca L1 je $lambda = c\/f_1 approx$ #br(B.lambda_cm, d: 2) cm, oko 1500 puta kraća od čipa C/A koda. Petlja faze nosioca (PLL) mjeri fazu s preciznošću od nekoliko milimetara, u simulatoru #br(B.faza_mm, d: 0) mm. Kvaka je u tome što prijemnik mjeri samo *dio* ciklusa i od trenutka zaključavanja broji cijele cikluse. Koliko je cijelih valnih duljina bilo između satelita i antene u prvom trenutku, ne zna. Fazno mjerenje u metrima je zato

$ Phi_i = rho_i + c (delta t - delta t^i) - I_i + T_i + lambda N_i + epsilon_(Phi,i) , $ <eq:faza>

gdje je $N_i$ nepoznat *cijeli broj* (cjelobrojna neodređenost), konstantan dok god prijemnik ne izgubi zabravu. Ionosfera fazu *ubrzava* ($-I$), a kod usporava ($+I$). Faza je izvanredno precizna, ali dvosmislena za cijeli broj ciklusa.

== Dvostruke razlike

Dva prijemnika, *rover* i *baza* na poznatom položaju, istodobno mjere iste satelite. *Jednostruka razlika* između prijemnika poništava sve što je zajedničko satelitu: sat satelita, a za kratku bazu i gotovo cijelu ionosferu, troposferu i pogrešku efemerida. *Dvostruka razlika* (DD) između dvaju satelita poništava i satove obaju prijemnika:

$ nabla Delta Phi^(i j) = nabla Delta rho^(i j) + lambda nabla Delta N^(i j) + nabla Delta epsilon , $ <eq:dd>

gdje je $nabla Delta$ razlika (rover − baza) razlike (satelit $j$ − referentni satelit $i$). Ostaju samo geometrija, cijeli broj $nabla Delta N^(i j)$ i milimetarski šum. Ostatak atmosfere raste s duljinom baze. Simulator ga modelira kao oko #B.atmo_ppm mm po kilometru (1 ppm).

== Float, fix i LAMBDA

RTK filtar u simulatoru (#kod("rtk.RTKFilter")) procjenjuje položaj rovera i neodređenosti zajedno, iz DD koda (glađenog, #br(B.kod_m, d: 1) m u zenitu) i DD faze. Postupak ima dva stupnja:

+ *Float rješenje.* Neodređenosti se procjenjuju kao realni brojevi. Dok se geometrija dovoljno ne promijeni, one su jako korelirane s položajem, pa je float rješenje u početku točno tek na decimetre.
+ *Fiksiranje (_ambiguity resolution_).* Kad je nesigurnost float neodređenosti dovoljno mala, traži se *najbliži cjelobrojni vektor* u metrici njihove kovarijance. Neodređenosti su međusobno jako korelirane, pa jednostavno zaokruživanje često griješi. Metoda LAMBDA (Teunissen) ih cjelobrojnom transformacijom dekorelira i u dekoreliranom prostoru učinkovito pretražuje kandidate.

Prijemnik smije prihvatiti cijele brojeve samo ako je siguran. Simulator traži dvoje:
- *ratio test*: drugi najbolji kandidat mora biti barem #br(B.ratio_min, d: 0) puta lošiji od najboljeg;
- vjerojatnost uspjeha (_bootstrapping_) od barem #br(B.p_boot * 100, d: 1) %.

Prihvaćeni cijeli brojevi se zatim „drže” (_fix-and-hold_). Pogrešan fiks je opasan, jer daje rješenje koje izgleda centimetarski, a pogrešno je za desetke centimetara. Zato se rješenje nakon fiksa još provjerava preko reziduala faze.

#figure(
  image("../slike/11-tijek.svg", width: 94%),
  caption: [Pogreška RTK-a od uključivanja, za bazu na 4 km (Zagreb, statičan rover). Iscrtkano: float rješenje. Puno: rješenje uz fiksirane neodređenosti.],
) <fig:rtktijek>

@fig:rtktijek prikazuje tipičan tijek. Sa sustavima GPS, Galileo i BeiDou filtar fiksira neodređenosti nakon #br(T3.ttf, d: 0) s, a pogreška tada padne na #br(T3.fix_med_cm, d: 1) cm (medijan). Samo s GPS-om FIX dolazi nakon #br(TG.ttf, d: 0) s, uz pogrešku od #br(TG.fix_med_cm, d: 1) cm. Više satelita znači više DD-ova i brže sužavanje nesigurnosti.

#napomena(naslov: "Zašto bez GLONASS-a")[
  GLONASS sateliti emitiraju na različitim frekvencijama (FDMA), pa im se valne duljine razlikuju. Dvostruka razlika između dva GLONASS satelita zato nema čisti cjelobrojni oblik @eq:dd. Simulator ih u RTK-u ne koristi. Stvarni prijemnici to rješavaju dodatnom kalibracijom.
]

== Duljina baze

Dvostruke razlike poništavaju atmosferu samo dok su rover i baza dovoljno blizu da im signali prolaze kroz istu atmosferu. S duljinom baze ostatak raste, a kad postane usporediv s dijelom valne duljine, cijeli brojevi se više ne mogu pouzdano razriješiti. @fig:baze prikazuje to u simulatoru (tri sustava, četiri sjemena × 600 s):

- *1 km:* FIX nakon #br(bz(1).ttf_med, d: 0) s, pogreška #br(bz(1).fix_err_cm, d: 1) cm;
- *5 km:* FIX nakon #br(bz(5).ttf_med, d: 0) s, pogreška #br(bz(5).fix_err_cm, d: 1) cm;
- *10 km:* FIX nakon #br(bz(10).ttf_med, d: 0) s, pogreška #br(bz(10).fix_err_cm, d: 1) cm, FIX u #br(bz(10).udio_fix, d: 0) % epoha;
- *20 km i više:* bez fiksa. Filtar zna da je atmosfera nesigurna (uključuje je u varijancu) i zato odbija riskirati pogrešan fiks.

#figure(
  image("../slike/11-baze.svg", width: 94%),
  caption: [Vrijeme do prvog fiksa (lijevo, medijan) i udio epoha s fiksom (desno) u ovisnosti o duljini baze, za GPS + Galileo + BeiDou. Iznad 20 km simulator ne fiksira.],
) <fig:baze>

U praksi se zato za RTK koriste mreže referentnih stanica na razmaku od nekoliko desetaka kilometara (u Hrvatskoj sustav CROPOS) ili tehnike virtualne referentne stanice, koje modeliraju atmosferu između stanica. Dvofrekvencijska mjerenja dodatno omogućuju kombinacije s duljom valnom duljinom (_wide-lane_, oko 86 cm), koje se fiksiraju lakše. Simulator koristi samo L1.

#kljucno[
  - Faza nosioca je milimetarski precizna, ali je dvosmislena za cijeli broj valnih duljina.
  - Dvostruke razlike poništavaju satove i, za kratke baze, atmosferu. Ostaju geometrija i cijeli brojevi.
  - FIX je odluka: bolje je ostati na float rješenju nego prihvatiti pogrešne cijele brojeve.
]

#vjezba(vrsta: "vodjena", naslov: "RTK uživo", rjesenje: [
  Nakon uključivanja #ui("RTK (fazni, cm)") status je najprije #ui("FLOAT"), uz pogrešku od nekoliko decimetara. Uz tri sustava za oko minutu prelazi u #ui("FIX"), a #ui("RTK greška") padne na oko centimetar. #ui("Ratio test") pri fiksiranju prijeđe 3. #ui("Vrijeme do FIX-a") ovisi o geometriji i iznosi desetke sekundi. Samo s GPS-om traje dulje, a u kinematičkom načinu rijetko dođe do fiksa (#ui("Kinematika samo s GPS L1 rijetko dođe do FIX-a — upali Galileo/BeiDou.")).
])[
  Postavi prijemnik, uključi GPS, Galileo i BeiDou te #ui("RTK (fazni, cm)"). U telemetriji prati #ui("Status"), #ui("RTK greška"), #ui("float greška"), #ui("Ratio test"), #ui("DD sateliti") i #ui("Vrijeme do FIX-a"). Ponovi samo s GPS-om. Usporedi kodnu pogrešku (#ui("Greška")) s RTK pogreškom.
]

#vjezba(vrsta: "vodjena", naslov: "Daleka baza", rjesenje: [
  Uz bazu na 2–5 km FIX dolazi brzo. Uz bazu na više od 20 km status ostaje #ui("FLOAT"), a float greška je decimetarska, kao na @fig:baze. Simulator pri tome ne prijavljuje lažni FIX: varijanca atmosfere raste s duljinom baze, pa ratio test i provjera vjerojatnosti uspjeha ne prolaze. Vraćanjem na #ui("Automatska baza") (oko 4 km) FIX se vraća.
])[
  Uz uključen RTK postavi baznu stanicu ručno: Shift + dvoklik na globus, redom na 2 km, 10 km i 30 km od rovera (#ui("Duljina baze") u telemetriji). Pričekaj nekoliko minuta simulacije za svaku. Kako se ponaša status? Vrati automatsku bazu gumbom #ui("Automatska baza").
]

#vjezba(vrsta: "racunska", naslov: "Što poništava dvostruka razlika", rjesenje: [
  Faza: $Phi_r^i = rho_r^i + c delta t_r - c delta t^i - I_r^i + T_r^i + lambda N_r^i + epsilon$. Jednostruka razlika rover − baza poništava $c delta t^i$ (isti satelit) i, za kratku bazu, većinu $I$, $T$ i pogreške efemerida (ista atmosfera i ista pogreška duž gotovo istog smjera). Dvostruka razlika satelit $j$ − satelit $i$ poništava $c(delta t_r - delta t_b)$, koji je zajednički svim satelitima. Neodređenost $nabla Delta N = (N_r^j - N_b^j) - (N_r^i - N_b^i)$ ostaje cijeli broj. Šum se pritom zbraja: četiri neovisna mjerenja daju $sigma_"DD" = 2 sigma$, tj. oko 4 mm za šum faze od 2 mm.
])[
  Napiši fazno mjerenje @eq:faza za rover i bazu prema satelitima $i$ i $j$. Pokaži koji članovi nestaju u jednostrukoj, a koji u dvostrukoj razlici. Je li $nabla Delta N$ cijeli broj? Koliki je šum dvostruke razlike ako svako fazno mjerenje ima šum od 2 mm?
]

#vjezba(vrsta: "racunska", naslov: "Atmosfera i duljina baze", rjesenje: [
  Uz 1 ppm ostatak na 10 km je 1 cm u zenitu i oko 5,8 cm na 10° ($1 \/ sin 10° approx 5","8$). To je četvrtina valne duljine (19 cm), pa pri niskim satelitima postaje usporedivo s polovicom ciklusa, gdje zaokruživanje postaje dvosmisleno. Na 40 km ostatak bi bio do oko 23 cm, više od cijele valne duljine. Granica od oko 20 km u simulatoru odgovara trenutku kad ostatak za niske satelite dosegne oko 1\/2 ciklusa.
])[
  Ako ostatak diferencijalne atmosfere iznosi 1 mm po kilometru baze u zenitu, a raste s $1\/sin "el"$, koliki je za bazu od 10 km i 40 km za satelit u zenitu i na 10°? Usporedi s valnom duljinom L1 i objasni zašto simulator iznad otprilike 20 km ne fiksira.
]

#vjezba(vrsta: "vodjena", naslov: "Eksperiment RTK i jedna nedosljednost", rjesenje: [
  Eksperiment daje gotovo iste brojke za bazu od 5, 30 i 60 km. Za zadanu masku od 15° i 10 epoha razmaka 30 s float pogreška je oko 6 cm, fiksna oko 1 mm, a #ui("Višeznačnost fiksirana") je uvijek #ui("DA"). S više epoha float se suzi (oko 1 cm uz 40 epoha). Razlog za neovisnost o duljini baze: offline model u eksperimentu (#kod("rtk.rtk_solve")) *ne uključuje ostatak diferencijalne atmosfere*, pa je svaka baza „kratka”. Živi RTK (#kod("rtk.LiveRTK")) atmosferu modelira i zato iznad 20 km ne fiksira (@fig:baze). Ova knjiga je tu razliku otkrila pri pisanju i predložena je kao ispravak simulatora. Pouka: rezultat modela vrijedi samo onoliko koliko i njegove pretpostavke.
])[
  U #ui("Eksperimenti…") otvori karticu #ui("RTK"). Pokreni ga za #ui("Baza istočno [km]") = 5, 30 i 60, svaki put uz #ui("Epohe") = 10 i 40. Zabilježi #ui("Float greška"), #ui("Fixed greška") i #ui("Višeznačnost fiksirana"). Usporedi s @fig:baze. Što je drukčije i zašto? Pogledaj izvorni kod #kod("rtk.rtk_solve") i #kod("rtk.CarrierPhaseSim.observe").
]
