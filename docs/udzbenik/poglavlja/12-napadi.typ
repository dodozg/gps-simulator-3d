#import "../predlozak.typ": *
#let B = json("../skripte/brojke_12.json")
#let V = B.vremenski
#let sp(x) = B.spoof.filter(p => p.x == x).first()
#let jm(ime, x) = B.jam.at(ime).filter(p => p.x == x).first()

= Ometanje i lažiranje <pog:napadi>


#cilj(
  [kako djeluju ometanje, meaconing te naivno i koordinirano lažiranje],
  [zašto je koordinirani lažni signal nevidljiv za RAIM],
  [koliko više sustava pomaže pod ometanjem i koje obrane postoje],
)

GNSS signal na Zemlji je slabiji od toplinskog šuma (pogl. @pog:signal), a njegova je struktura javno objavljena. Iz toga slijede dvije ranjivosti. Signal je lako *ugušiti* (ometanje, _jamming_) i lako *oponašati* (lažiranje, _spoofing_). Oba napada danas nisu teorija: ometala za nekoliko desetaka eura prodaju se kao „zaštita privatnosti”, a lažni signali zabilježeni su u pomorstvu i zrakoplovstvu. Ovo poglavlje pokazuje kako svaki napad djeluje na prijemnik i koje ga obrane vide.

== Četiri napada

Simulator modelira četiri tipična napada (#kod("spoofing.py")). Ometanje djeluje u *signalu*: podiže šumni pod prije praćenja. Lažiranje djeluje na *mjerenja*: mijenja pseudoudaljenosti prije rješavanja. Svaki napad prolazi kroz isti Kalmanov filtar i RAIM kao i u živoj simulaciji.

- *Ometanje.* Širokopojasni ometač s omjerom $J\/N$ smanjuje C/N0 svih satelita prema @eq:jam. Najslabiji, niski sateliti prvi padaju ispod praga zabrave, a preživjelima raste šum koda. Prijemnik ih zato sam otežava, pa ometanje ne izaziva lažne alarme. Ono ne laže, nego gasi.
- *Meaconing.* Napadač prima stvarne signale i reemitira ih s kašnjenjem. Ako je kašnjenje svima isto, ono je za prijemnik nerazlučivo od pogreške vlastitog sata.
- *Naivni lažni signal.* Nekoliko satelita dobije velike, međusobno neovisne pomake. Mjerenja postaju nedosljedna.
- *Koordinirani lažni signal* (_seamless takeover_). Napadač zna gdje je žrtva i svakom satelitu doda upravo onoliki pomak koji odgovara razlici udaljenosti do *ciljne* točke. Mjerenja su međusobno savršeno dosljedna, samo opisuju pogrešno mjesto. Pomak se uvodi postupno, kroz rampu, da filtar ne bi primijetio skok.

#figure(
  image("../slike/12-napadi.svg", width: 100%),
  caption: [Četiri napada kroz vrijeme (Zagreb, samo GPS, napad počinje u 60 s i doseže punu snagu u 180 s). Plavo: pogreška položaja (log-mjerilo). Sivo: broj praćenih satelita (desna os). Crveni križići: epohe s RAIM alarmom ili isključenjem.],
) <fig:napadi>

@fig:napadi pokazuje ishod:

- *koordinirani lažni signal* pomaknuo je rješenje na #br(V.coordinated.pogreska_kraj, d: 0) m od istine, a #br(V.coordinated.cilj_kraj) m od cilja napadača, uz *#V.coordinated.alarmi* RAIM alarma;
- *naivni lažni signal* RAIM je otkrio u svakoj epohi napada (#V.naive.alarmi alarma, prvi već u #V.naive.prvi_alarm s), isključio pokvarene satelite i zadržao pogrešku na #br(V.naive.pogreska_kraj) m;
- *meaconing* nije pomaknuo položaj (#br(V.meaconing.pogreska_kraj) m): zajednički pomak od 4 km upio je sat prijemnika;
- *ometanje* je broj satelita svelo sa #V.jamming.sateliti_prije na #V.jamming.sateliti_min, a fix je izostao u #V.jamming.bez_fixa epoha.

#kljucno[
  - RAIM vidi *nedosljednost*, a ne *laž*. Dosljedna laž je za njega nevidljiva.
  - Zajednički pomak svih satelita završava u satu prijemnika, a ne u položaju.
  - Ometanje ne vara prijemnik, nego ga zaslijepi. Zato je lakše otkriti, ali ga je teško spriječiti.
]

== Koordinirani lažni signal i integritet

Koliko je opasan koordinirani napad? Studija u sandboxu (#kod("sandbox/examples/spoof_offset.json"), Zagreb, 10 sjemena × 200 s) mijenja pomak cilja od 0 do 800 m. Konačna pogreška točno slijedi pomak (#br(sp(800).final_err, d: 0) m za cilj od 800 m), a RAIM gotovo ništa ne primjećuje (u prosjeku #br(sp(800).raim_detections, d: 1) detekcija po runu, slučajnih). Medijan zaštitne granice ostaje oko #br(sp(800).hpl_median, d: 0) m, jer napad ne mijenja ni geometriju ni šum. Udio epoha s lažnom informacijom (pogreška veća od HPL-a bez alarma) raste s #br(sp(50).mi_rate * 100, d: 0) % za pomak od 50 m do #br(sp(800).mi_rate * 100, d: 0) % za 800 m. Iznad granice uzbune od 556 m pojavljuju se i opasne lažne informacije: u prosjeku #br(sp(800).hmi_events, d: 0) epoha po runu.

Integritet je pritom cijelo vrijeme „dostupan” (HPL ≤ HAL), pa prijemnik s mirnom savješću tvrdi da je točan na 47 m dok je zapravo 800 m daleko. To je najopasnija moguća situacija, i upravo je zato koordinirano lažiranje glavna prijetnja sigurnosno kritičnim primjenama.

Obrane postoje, ali nijedna nije dio klasičnog RAIM-a:
- *provjera s drugim senzorom*: inercijalna navigacija, odometrija ili barometar ne slažu se s postupnim „odlaskom”;
- *provjera signala*: snaga signala (lažni je često prejak i jednak za sve satelite), smjer dolaska (antenski niz), nagla promjena C/N0 ili Dopplera;
- *kriptografska autentikacija* navigacijske poruke, kakvu danas nudi Galileo OSNMA, koja dokazuje da poruku šalje stvarni satelit.

== Ometanje i redundancija

Studija ometanja (#kod("sandbox/examples/jamming_jn.json"), Zagreb, 6 sjemena, ometač uključen od $t$ = 30 s) mijenja $J\/N$ i uspoređuje samo GPS sa sva četiri sustava (@fig:jamstudija, desno):

- do 14 dB oba prijemnika imaju fix u svim epohama napada, ali GPS-u zaštitna granica raste (medijan HPL-a #br(jm("GPS", 14).hpl_median, d: 0) m pri 14 dB, uz #br(jm("GPS", 0).hpl_median, d: 0) m bez ometanja) i dostupnost integriteta pada na #br(jm("GPS", 14).integrity_availability * 100, d: 0) %;
- pri 16 dB GPS ima fix u #br(jm("GPS", 16).win_availability * 100, d: 0) % epoha, a četiri sustava u #br(jm("četiri sustava", 16).win_availability * 100, d: 0) %;
- pri 18 dB GPS je bez fixa, a četiri sustava ga još imaju u #br(jm("četiri sustava", 18).win_availability * 100, d: 0) % epoha.

#figure(
  image("../slike/12-studije.svg", width: 100%),
  caption: [Lijevo: koordinirani lažni signal. Udio epoha s lažnom informacijom raste s pomakom cilja, a RAIM ga ne otkriva. Desno: udio epoha s fixom za vrijeme ometanja u ovisnosti o $J\/N$, za samo GPS i za četiri sustava (sandbox, EKF).],
) <fig:jamstudija>

Ometač istim $J\/N$ pogađa sve sustave, pa multi-GNSS ne pomaže jer bi bio „jači”, nego zato što preživi više satelita. Nekoliko decibela tolerancije više znači, uz $1\/r^2$ slabljenje snage ometala, primjetno manji polumjer u kojem ometalo onesposobljava prijemnik.

Studija otkriva i jedan kompromis. Bez ometanja medijan HPL-a s četiri sustava (#br(jm("četiri sustava", 0).hpl_median, d: 0) m) veći je nego samo s GPS-om (#br(jm("GPS", 0).hpl_median, d: 0) m). Uz granicu od deset satelita u rješenju (pogl. @pog:dop) četiri sustava znače četiri sata, odnosno tri nepoznanice više, pa ostaje manje redundancije za zaštitnu granicu. Više sustava, ali premalo satelita po sustavu, može oslabiti integritet.

#vjezba(vrsta: "vodjena", naslov: "Četiri napada uživo", rjesenje: [
  Ishodi odgovaraju @fig:napadi[slici]. Uz koordinirani lažni signal procjena (na globusu) glatko odšeta od stvarnog položaja dok #ui("Integritet") cijelo vrijeme pokazuje #ui("u redu"), a krug HPL-a ostaje zelen i mali. Uz naivni napad u tablici se pojave sateliti #ui("RAIM odbacio"), a status je #ui("kvar isključen"). Meaconing ne mijenja položaj, ali se pomak vidi u procjeni sata prijemnika (#ui("Sat prijemnika")), koja kroz rampu napada naraste za kašnjenje od 4 km. Ometanje smanjuje C/N0 svih satelita, sateliti nestaju iz tablice počevši od najnižih, a na kraju nestaje i fix.
])[
  U lijevom panelu pod #ui("Napad") redom odaberi #ui("koordinirani spoof"), #ui("naivni multi-SV"), #ui("meaconing") i #ui("jamming"). Za svaki napad pričekaj da prozor napada prođe (#ui("NAPAD AKTIVAN")) i prati #ui("Greška"), #ui("Integritet"), tablicu satelita i krug HPL-a na globusu. Između napada vrati #ui("bez napada").
]

#vjezba(vrsta: "vodjena", naslov: "Spoof jednog satelita", rjesenje: [
  Pomak emitirane pozicije satelita od 50 m za prijemnik izgleda kao pogreška od približno 50 m duž linije pogleda (ovisno o kutu između radijalnog smjera i linije pogleda). Mali pomaci (nekoliko metara) prolaze neotkriveni. Veći, od nekoliko desetaka metara, RAIM uglavnom otkrije i satelit se isključi (usporedi s kvarom sata, @fig:roc). Ovo je naivni napad na jedan satelit, pa redundancija pomaže.
])[
  U editoru jednog satelita postavi #ui("Spoof pozicije [m]") na 10, 50 i 200. Što se događa sa statusom integriteta i s rezidualom tog satelita (#ui("Rezidual"))? Usporedi s ubrizgavanjem kvara sata iste veličine.
]

#vjezba(vrsta: "vodjena", naslov: "Scenarij s usporedbom", rjesenje: [
  Usporedba prikazuje dva stupca metrika za isti scenarij: s isključenim i s uključenim RAIM-om. Uz naivni napad bez RAIM-a medijan i najveća pogreška narastu na stotine ili tisuće metara. S RAIM-om ostaju na metrima, a pojavljuju se RAIM alarmi (isključenja). Uz koordinirani napad oba stupca su gotovo jednaka, jer RAIM nema što vidjeti. Polje #ui("Udaljenost od cilja napada") pokazuje da je napadač postigao cilj.
])[
  U #ui("Eksperimenti…") otvori karticu #ui("Scenariji"). Odaberi scenarij #kod("naive_spoof") i klikni #ui("Usporedi (RAIM on/off)"). Usporedi metrike. Ponovi sa scenarijem #kod("spoof_coordinated").
]

#vjezba(vrsta: "racunska", naslov: "Doseg ometala", rjesenje: [
  Snaga ometala na prijemniku pada s $1\/r^2$, pa svakih 6 dB manje potrebnog $J\/N$ znači dvostruku udaljenost. Ako GPS-prijemnik gubi fix pri 16 dB, a multi-GNSS tek pri 18 dB, ometalo istog odašiljanja onesposobljava GPS-prijemnik do udaljenosti $r_0$, a multi-GNSS do $r_0 dot 10^(-2\/20) approx 0","79 r_0$. Površina ugroženog područja smanjuje se na $0","79^2 approx 63$ %. Apsolutni doseg ovisi o snazi ometala, širini pojasa, antenama i terenu. Ova knjiga ga ne računa.
])[
  Pretpostavi slobodni prostor ($J prop 1\/r^2$). Prijemnik gubi fix pri $J\/N$ = 16 dB samo s GPS-om, a pri 18 dB sa svim sustavima. Za koliko se smanjuje udaljenost i površina unutar koje isto ometalo onesposobljava prijemnik?
]

#vjezba(vrsta: "istrazivacka", naslov: "Napad koji RAIM vidi napola", rjesenje: [
  Djelomično koordiniran napad, kada se pomakne samo dio satelita, ostavlja rezidual proporcionalan dijelu koji nije usklađen. RAIM ga otkriva kad taj dio prijeđe prag sličan onome iz @fig:roc[slike]. Odgovor ovisi o tvom pluginu i nije unaprijed izračunat u ovoj knjizi. Očekuje se da napadač koji kontrolira samo pola satelita ne može glatko preuzeti položaj bez alarma.
])[
  Napiši vlastiti napad u sandboxu (#kod("@register_attack"), pogl. @pog:projekti) koji koordinirano laže samo na polovici satelita, a ostale ostavlja netaknute. Usporedi #kod("raim_detections"), #kod("mi_rate") i #kod("final_err") s potpuno koordiniranim napadom. Što zaključuješ o tome koliko satelita napadač mora kontrolirati?
]
