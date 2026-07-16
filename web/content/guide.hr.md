# GPS Simulator 3D — objašnjeno kao da imaš 13 godina

Zamisli da želiš napraviti **virtualni GPS sustav unutar računala**.

U tom virtualnom svijetu postoje:

* sateliti koji kruže oko Zemlje
* GPS prijamnik na tlu, primjerice mobitel ili automobil
* radio-signali koji putuju od satelita do prijamnika
* atmosfera koja malo usporava signale
* planine koje mogu zakloniti satelite
* pogreške satova i položaja satelita
* program koji iz svega toga pokušava izračunati gdje se prijamnik nalazi

To je ono što radi **GPS Simulator 3D**.

Nije samo animacija satelita. Iza 3D prikaza nalazi se pravi matematički sustav koji pokušava riješiti isti osnovni problem koji rješava GPS prijamnik u mobitelu.

## 1. Najjednostavnija slika cijelog projekta

Projekt možemo zamisliti kao automobil.

### Engine je motor

Python program računa:

* gdje se sateliti nalaze
* kako se kreću
* koliko dugo signal putuje
* kakve pogreške nastaju
* gdje se prijamnik vjerojatno nalazi

Motor može raditi i bez grafike.

### Web i desktop su upravljačka ploča

Oni prikazuju rezultate motora:

* web verzija prikazuje Zemlju i satelite u pregledniku
* desktop verzija prikazuje 3D scenu u zasebnoj aplikaciji
* CLI alati pokreću posebne eksperimente bez grafičkog sučelja

Drugim riječima:

> Engine razmišlja i računa, a sučelja pokazuju što se događa.

## 2. Kako GPS uopće zna gdje se nalaziš?

Svaki satelit stalno šalje poruku koja približno govori:

> Ja sam satelit broj 12. Trenutačno sam ovdje. Ovu sam poruku poslao u točno određeno vrijeme.

GPS prijamnik mjeri koliko je dugo poruka putovala.

Budući da radio-signal putuje približno brzinom svjetlosti, može se izračunati udaljenost:

```text
udaljenost = brzina svjetlosti × vrijeme putovanja
```

Ako znaš udaljenost do jednog satelita, znaš samo da se nalaziš negdje na velikoj kugli oko njega.

S dva satelita dobiješ uži skup mogućih položaja. S tri satelita možeš približno odrediti položaj.

U praksi su potrebna najmanje **četiri satelita**, jer prijamnik mora izračunati:

1. položaj istok–zapad
2. položaj sjever–jug
3. visinu
4. pogrešku vlastitog sata

Prijamnik u simulatoru obično koristi više satelita kako bi rezultat bio stabilniji.

## 3. Što rade pojedini dijelovi simulatora?

### physics_engine.py — profesor fizike

Ovaj modul računa fizičke pojave: kretanje satelita, gravitacijske utjecaje, usporavanje signala u atmosferi, rotaciju Zemlje, pogreške satova i relativističke efekte.

Relativnost zvuči kao nešto iz znanstvene fantastike, ali GPS je stvarno mora uzeti u obzir. Satelitski satovi ne rade potpuno jednakom brzinom kao satovi na Zemlji.

### satellite.py — voditelj satelita

Ovaj dio stvara i organizira satelite. Može simulirati četiri sustava:

* **GPS** — američki
* **Galileo** — europski
* **GLONASS** — ruski
* **BeiDou** — kineski

Kada su svi uključeni, simulator može imati oko **96 satelita**. Naravno, prijamnik ne vidi svih 96 odjednom — mnogi se u tom trenutku nalaze na drugoj strani Zemlje ili su prenisko iznad horizonta.

### signal_processing.py — virtualna antena i radio

Ovaj modul pokušava oponašati primanje GPS signala. Svaki satelit ima poseban digitalni uzorak koji se zove **PRN kod**. Zamisli ga kao poseban ritam:

```text
satelit 1: + - + + - - + ...
satelit 2: - + - - + + - ...
```

Prijamnik poznaje te uzorke. U primljenom šumu traži trenutak u kojem se njegov lokalni uzorak najbolje poklapa sa signalom. To se zove **korelacija**, a slično je pokušaju da u bučnoj prostoriji prepoznaš poznatu melodiju.

Simulator signal provjerava osam puta detaljnije nego prije, pa može preciznije odrediti trenutak dolaska signala, a time i udaljenost do satelita.

### terrain.py — karta reljefa

Ovaj dio zna gdje se nalaze planine, doline, uzvisine i kolika je stvarna visina tla. Ako se između prijamnika i satelita nalazi planina, signal može biti blokiran. Simulator zato ne provjerava samo je li satelit iznad horizonta, nego i postoji li stvarna, nezaklonjena linija između prijamnika i satelita.

### receiver.py — virtualni GPS prijamnik

Ovo je glavni dio projekta. On:

1. pronalazi vidljive satelite
2. bira korisne satelite
3. obrađuje njihove signale
4. ispravlja poznate pogreške
5. računa položaj
6. provjerava šalje li neki satelit neobične podatke

To je „mozak” cijelog simulatora.

## 4. Kako izgleda jedan krug simulacije?

Web aplikacija taj postupak ponavlja otprilike **10 puta u sekundi**:

1. Sateliti se pomaknu po svojim orbitama.
2. Izračuna se koji su sateliti vidljivi.
3. Svaki vidljivi satelit pošalje virtualni signal.
4. U signal se dodaju šum i fizičke pogreške.
5. Prijamnik mjeri udaljenosti.
6. Matematički filtar procjenjuje položaj.
7. Sustav provjerava postoje li sumnjiva mjerenja.
8. Novi rezultat šalje se web-pregledniku.
9. Cesium osvježava globus, satelite i grafikone.

Sve se to događa dovoljno brzo da izgleda kao živa simulacija.

## 5. Zašto GPS mjerenje nije savršeno?

Signal ne putuje kroz idealan, prazan prostor.

### Ionosfera

Visoki sloj atmosfere s električki nabijenim česticama usporava signal. Različite radio-frekvencije usporavaju se različito, pa prijamnik može usporediti signale na dvije frekvencije, L1 i L2, i ukloniti velik dio ionosferske pogreške. To je **iono-free kombinacija**. Loša strana je što se tako pojačava dio običnog šuma.

### Troposfera

Niži dio atmosfere, u kojem živimo i u kojem nastaju oblaci, također usporava signal. Za razliku od ionosfere, ta se pogreška ne može ukloniti usporedbom L1 i L2 signala, pa simulator koristi matematički model atmosfere.

### Multipath

Signal se može odbiti od zgrade, tla, stijene ili metalne površine. Prijamnik tada dobije izravni signal i jednu ili više zakašnjelih kopija. To je kao jeka: ako vikneš u tunelu, čuješ izvorni glas i njegove odjeke. GPS prijamnik zbog toga može pomisliti da je signal putovao malo dulje nego što stvarno jest.

### Šum

Radio-signali su izrazito slabi, a elektronika i okolina stvaraju nasumične smetnje. Simulator zato dodaje **AWGN**, odnosno vrstu matematički modeliranog bijelog šuma.

### Pogreška položaja satelita

Prijamnik ne zna savršeno gdje se satelit nalazi — koristi podatke o orbiti koje mu šalje satelit. Ti podaci mogu sadržavati malu pogrešku. U simulatoru se ona mijenja polako, jer se ni stvarne pogreške satelitskih orbita ne mijenjaju potpuno nasumično svake desetinke sekunde.

### Sagnacov efekt

Dok signal putuje od satelita do prijamnika, Zemlja se nastavlja okretati. Signal putuje samo djelić sekunde, ali GPS pokušava mjeriti položaj u metrima, pa i tako mala rotacija Zemlje postaje važna. Ako se taj efekt pogrešno primijeni, izračunati položaj može biti pomaknut desetke metara.

## 6. Što je EKF?

EKF znači **Extended Kalman Filter**, odnosno prošireni Kalmanov filtar.

Zamisli da pratiš biciklista, ali ga ne možeš stalno jasno vidjeti. U jednom trenutku znaš gdje je bio, kojom se brzinom kretao i u kojem je smjeru išao, pa možeš predvidjeti gdje bi trebao biti za sekundu. Kada dobiješ novo, pomalo netočno mjerenje, usporediš ga s predviđanjem.

Kalmanov filtar stalno kombinira **ono što očekuje** i **ono što je upravo izmjerio**, i ne vjeruje potpuno ni jednom ni drugom.

Simulatorov filtar prati **11 vrijednosti**:

* 3 vrijednosti položaja
* 3 vrijednosti brzine
* pogrešku sata
* promjenu pogreške sata
* 3 razlike između vremenskih sustava Galileo, GLONASS i BeiDou

### Kako počinje ako još ništa ne zna?

Na početku simulator koristi metodu **najmanjih kvadrata** (least squares) za prvi grubi izračun položaja. Nakon toga EKF preuzima praćenje i postupno poboljšava procjenu.

> Least squares pronađe početni položaj, a EKF ga zatim prati i zaglađuje.

## 7. Što je RAIM?

RAIM je sustav koji provjerava slažu li se satelitska mjerenja.

Zamisli da pet prijatelja pokušava pogoditi koliko je udaljena škola:

* prvi kaže 800 m
* drugi kaže 810 m
* treći kaže 790 m
* četvrti kaže 805 m
* peti kaže 6 km

Peti odgovor očito izgleda sumnjivo. RAIM radi nešto slično: traži satelit čije se mjerenje jako razlikuje od ostalih i može ga izbaciti iz izračuna.

Ali RAIM ima važno ograničenje. Ako **svi satelitski signali zajedno daju istu, dobro usklađenu laž**, RAIM možda neće shvatiti da nešto nije u redu — sva se mjerenja međusobno slažu, iako vode na pogrešno mjesto. To nije pogreška ovog simulatora, nego stvarno ograničenje takve vrste zaštite.

## 8. Zašto simulator ne koristi uvijek sve satelite?

Više satelita obično pomaže, ali nije svaki satelit jednako koristan. Satelit visoko na nebu obično daje bolji signal, dok satelit vrlo nisko iznad horizonta ima dulji put kroz atmosferu i češće stvara probleme s refleksijama.

Simulator zato bira do deset satelita koji daju dobru geometriju. Dobra geometrija znači da su sateliti lijepo raspoređeni po nebu, a ne nagurani u istom smjeru.

### GDOP

**GDOP** je broj koji opisuje koliko je dobar raspored satelita: manji GDOP znači bolju geometriju, veći GDOP lošiju. Zamisli da pokušavaš pronaći točku presjeka nekoliko crta — ako sve dolaze iz gotovo istog smjera, mala pogreška može jako pomaknuti rezultat; ako dolaze iz različitih smjerova, položaj je lakše odrediti.

## 9. Što je ISB?

GPS, Galileo, GLONASS i BeiDou ne koriste potpuno jednaku vremensku skalu. To stvara male razlike u mjerenim udaljenostima, koje se zovu **inter-system bias** (ISB).

Primjerice, signal iz jednog sustava može izgledati kao da je putovao nekoliko metara više ili manje, iako je stvarni razlog razlika između satova sustava. Simulator namjerno dodaje te razlike, a EKF ih zatim pokušava procijeniti — dakle ne pravi se da su svi sustavi savršeno sinkronizirani.

## 10. Što znače NIS i DOP?

### NIS — je li filtar realističan?

NIS provjerava odgovaraju li stvarne pogreške onome što filtar očekuje. Vrlo pojednostavljeno:

* NIS oko 1: filtar dobro procjenjuje koliko su mjerenja bučna
* stalno iznad 1: filtar je previše samouvjeren
* stalno ispod 1: filtar je previše oprezan

To je kao učenik koji prije testa procjenjuje koliko zna: ako očekuje peticu, a stalno dobiva dvojku, previše je samouvjeren; ako očekuje dvojku, a stalno dobiva peticu, previše je oprezan.

### DOP — koliko je dobar raspored satelita?

DOP govori koliko će geometrija satelita povećati pogreške mjerenja. Čak i uz kvalitetne signale, loš raspored satelita može dati lošu poziciju.

## 11. Koliko je simulator točan?

Projekt je prije imao pogrešku od približno **50 metara**. Nakon brojnih popravaka došao je na približno:

* tipičnu pogrešku: **4–6 metara**
* u većini težih slučajeva: **6–10 metara**
* povremene vrhove: približno **12–15 metara**

To je realno za klasično satelitsko određivanje položaja bez posebne zemaljske korekcijske stanice. Nije sustav centimetarske preciznosti poput naprednog RTK-a.

## 12. Kako je pogreška smanjena s 50 na oko 5 metara?

To je jedan od najzanimljivijih dijelova projekta.

### Problem 1: pregrubo mjerenje signala

Prijašnja obrada signala mogla je razlikovati udaljenosti uz pogrešku od otprilike 27 metara. Rješenje je bilo osam puta detaljnije uzorkovanje signala i preciznije pronalaženje vrha korelacije, čime je pogreška mjerenja spuštena na približno nekoliko metara.

### Problem 2: Sagnacova korekcija nije bila dosljedna

Prijamnik je pokušavao ukloniti rotaciju Zemlje, ali ta pojava nije bila pravilno dodana u simulirano mjerenje. Bilo je to kao da kalkulator oduzme 25 iako prije toga nitko nije dodao 25. Rezultat je bio pomak prema istoku od približno 25 metara. Kada je model ispravljen na obje strane, pogreška je nestala.

### Problem 3: troposfera nije bila ispravljena

Ionosferska korekcija ne uklanja troposfersku pogrešku, pa je dodan poseban model za troposferu.

### Problem 4: previše radio-šuma

Stari parametri pretpostavljali su previše šuma, pa su postavljeni na realističniju razinu.

### Problem 5: filtar je pogrešno procjenjivao kvalitetu mjerenja

Parametri Kalmanova filtra podešeni su tako da njegov NIS bude približno 1, što znači da je filtar počeo točnije procjenjivati vlastitu nesigurnost.

## 13. Zašto su neke realističnije promjene pogoršale rezultat?

To je važno razumjeti:

> Realističniji simulator ne mora uvijek davati ljepše rezultate.

Ako umjetno postaviš da su sve pogreške potpuno nasumične, Kalmanov filtar ih može lako usrednjiti. Ali neke stvarne pogreške traju dugo i ne nestaju jednostavnim prosjekom.

Kada je uveden realističniji model pogreške orbite satelita, pogreška položaja ponegdje je porasla, primjerice s oko 4,5 na 5,6 metara. To nije kvar — stari model bio je previše optimističan.

Slično je videoigri: možeš isključiti vjetar i kišu pa će vožnja biti lakša; ako ih uključiš, rezultat može biti lošiji, ali simulacija postaje stvarnija.

## 14. Što prikazuje web-aplikacija?

Web-aplikacija je kontrolni centar simulatora. U njoj se može:

* gledati Zemlju u 3D
* pratiti satelite i njihove orbite
* vidjeti koji su sateliti uključeni
* uključivati GPS, Galileo, GLONASS i BeiDou
* premještati prijamnik
* ubrzavati ili zaustavljati vrijeme
* uključivati i isključivati RAIM
* pratiti pogrešku položaja, GDOP i NIS
* izvoditi eksperimente i prolaziti vođene lekcije
* mijenjati parametre pojedinog satelita
* simulirati kvarove i smetnje

Backend računa simulaciju, a frontend prikazuje rezultate na globusu. Povezani su WebSocketom, što znači da veza ostaje otvorena i server stalno šalje nova stanja bez ponovnog učitavanja stranice.

## 15. Koliko je projekt „stvaran”, a koliko pojednostavljen?

### Stvarni i ozbiljni dijelovi

Projekt stvarno koristi: računanje orbita, korekciju atmosferskih pogrešaka, Sagnacov efekt, satelitske i prijamničke satove, obradu PRN signala, određivanje položaja, 11-stanjski Kalmanov filtar, RAIM, rad s više GNSS sustava, razlike između njihovih vremenskih skala, stvarni model terena i statističke provjere kvalitete. To nisu samo unaprijed nacrtane animacije.

### Pojednostavljeni dijelovi

Signalni dio još nije potpuno jednak stvarnom GPS prijamniku:

* PRN kodovi nisu pravi GPS Gold kodovi
* nema potpunog modela Dopplerova pomaka
* nema pravog praćenja faze nositelja
* nema punog dekodiranja navigacijskih poruka
* nema pravog ulaza s antene
* dio parametara podešen je da daje realistične rezultate, ali nije izveden iz cijelog fizičkog radio-linka

Zato je najbolji opis:

> Matematički i navigacijski dio vrlo je ozbiljan, dok je radio-signal još pojednostavljen.

## 16. Može li raditi sa stvarnim GPS podacima?

Velik dio može. Trenutačno simulator sam proizvodi virtualna mjerenja. Da bi radio sa stvarnim GPS prijamnikom, trebalo bi dodati dio koji čita sirove izmjerene udaljenosti, podatke iz RINEX datoteka, podatke iz stvarnog GNSS uređaja, stvarne podatke o orbitama satelita i satelitske korekcije satova.

Nakon toga postojeći solver mogao bi pokušati izračunati stvarnu poziciju. Ali za centimetarsku preciznost trebalo bi dodati **carrier-phase** obradu i potpuni RTK sustav.

## 17. Kako projekt provjerava da nešto nije pokvareno?

Projekt ima oko **60 automatskih testova**. Oni provjeravaju pretvaranje koordinata, položaje satelita, obradu signala, izračun položaja, RAIM, teren, spoofing eksperimente, web-backend i statističko ponašanje filtra.

Posebno je važan **zero-noise test**. U njemu se isključe šum, multipath, pogreške orbita, pogreške satova i pogreške mjerenja. Ako se svi fizički modeli i korekcije savršeno poklapaju, rezultat mora biti gotovo potpuno točan. Ako se pojavi pogreška od nekoliko metara, to znači da je neki efekt:

* dodan, ali nije uklonjen
* uklonjen, ali nije bio dodan
* izračunat drukčije u mjerenju i prijamniku

To je najbolji način da se pronađu tihi bugovi poput starog Sagnacova problema.

## 18. Koje su najveće prednosti projekta?

1. **Nije samo lijepa animacija** — 3D prikaz je samo vanjski sloj; iza njega stvarno radi navigacijski algoritam.
2. **Pokazuje zašto GPS griješi** — utjecaj atmosfere, lošeg rasporeda satelita, refleksija, kvarova satelita, netočnih satova i različitih GNSS sustava.
3. **Dobar je za učenje** — umjesto da samo čitaš definiciju GDOP-a ili RAIM-a, možeš promijeniti uvjete i odmah vidjeti rezultat.
4. **Dobro je testiran** — automatski testovi smanjuju mogućnost da nova promjena neprimjetno pokvari postojeću funkcionalnost.
5. **Iskreno opisuje pojednostavljenja** — dokumentacija ne tvrdi da je svaki dio savršena kopija stvarnog GPS prijamnika.

## 19. Koje su najveće slabosti?

### Signalni dio nije potpuno realističan

Za pravi softverski GPS prijamnik trebalo bi mnogo detaljnije simulirati radio-signal.

### receiver.py radi previše stvari

Jedna datoteka upravlja obradom kanala, korekcijama, izborom satelita, EKF-om i RAIM-om. Bilo bi preglednije podijeliti je u nekoliko manjih dijelova.

### Postoje dva grafička sučelja

Desktop i web verzija djelomično rade istu stvar, što dugoročno znači dvostruko održavanje. Web verzija izgleda kao logičniji smjer razvoja.

### Projekt se nalazi na Google Driveu

To uzrokuje tehničke probleme s velikim brojem malih datoteka, posebno s `node_modules`. Bolje bi bilo držati aktivni repozitorij na lokalnom SSD-u, a Git koristiti za sinkronizaciju i sigurnosnu kopiju.

## 20. Konačna ocjena jednostavnim riječima

Ovaj projekt je mnogo više od školske demonstracije satelita. Najbolje ga je opisati kao:

> Virtualni GPS laboratorij u kojem računalo glumi satelite, atmosferu, radio-kanal i prijamnik.

Njegov najjači dio nije 3D grafika, nego činjenica da stvara nesavršena mjerenja, pokušava ih ispraviti stvarnim algoritmima, procjenjuje vlastitu nesigurnost, prepoznaje neka neispravna mjerenja i omogućuje promatranje cijelog postupka uživo.

Ocjena **8/10** ima smisla: kao alat za učenje izvrstan, kao istraživački laboratorij vrlo dobar, a kao pravi GPS prijamnik ima snažnu jezgru, ali još mu nedostaje pravi ulaz s antene i potpuniji signalni sloj.

### U jednoj rečenici

**GPS Simulator 3D je kao vrlo napredna videoigra za GPS: sateliti, atmosfera i pogreške simulirani su u računalu, a pravi matematički „GPS mozak” pokušava iz šumovitih signala pronaći položaj s pogreškom od nekoliko metara.**
