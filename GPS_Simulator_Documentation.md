# GPS Simulator 3D - Kompletna Tehnička Dokumentacija

Ovaj dokument pruža detaljan pregled arhitekture, implementiranih algoritama i fizičkih fenomena unutar **GPS Simulatora 3D**. Projekt je evoluirao iz jednostavnog geometrijskog kalkulatora u visokofidelitetni inženjerski simulator sposoban testirati state-of-the-art navigacijske algoritme.

## 1. Arhitektura Softvera

Sustav je modularno podijeljen u pet ključnih komponenti:
- **`main.py`**: Glavna kontrolna petlja i 3D vizualizacija bazirana na PyVista/VTK engineu. Upravlja interakcijom s korisnikom i iscrtavanjem terena, satelita i prijemnika.
- **`physics_engine.py`**: Srce astrodinamike i fizike kanala. Sadrži modele Zemljine gravitacije, atmosferska kašnjenja i efekte teorije relativnosti.
- **`receiver.py`**: Navigacijski procesor. Bavi se rješavanjem pozicije, obradom pseudoudaljenosti i filtriranjem pogrešaka.
- **`satellite.py`**: Simulira konstelaciju satelita (Walker-Delta konfiguracija) i rad njihovih unutarnjih atomskih satova.
- **`signal_processing.py`**: Baseband procesor koji vrši digitalnu obradu signala (DSP) u frekventnom domenu radi korelacije PRN (Pseudo-Random Noise) kodova.

---

## 2. Prijemnik i Obrada Signala (Receiver & DSP)

### 2.1. Dual-Frequency Iono-Free Kombinacija
Simulator podržava višekanalni prijem (L1 frekvencija: 1575.42 MHz i L2 frekvencija: 1227.60 MHz). Prijemnik koristi linearnu Iono-Free matematičku kombinaciju mjerenja s ova dva opsega kako bi gotovo u potpunosti eliminirao kašnjenje signala nastalo prolaskom kroz ionosferu.

### 2.2. FFT Korelacija Signala
U modulu `signal_processing.py`, detekcija signala se ne vrši običnom "geometrijskom distancom", već fizičkom korelacijom. Signali se prebacuju u frekventnu domenu (FFT), dodaje im se AWGN (Additive White Gaussian Noise) šum kanala i simulira se slabljenje amplitude (Multipath Fading). Dekodiranjem vrhova korelacije (correlation peaks) izvlači se precizna pseudoudaljenost.

---

## 3. Navigacijski Algoritmi (Positioning Engine)

### 3.1. Extended Kalman Filter (EKF)
Srž prijemnika je napredni 8-dimenzionalni Extended Kalman Filter. On istovremeno prati:
- 3D Poziciju ($x, y, z$)
- 3D Brzinu ($v_x, v_y, v_z$)
- Hardverski pomak sata ($c \cdot bias$)
- Brzinu promjene sata ($c \cdot drift$)

EKF dinamički ispravlja pogreške hardvera u realnom vremenu, oslanjajući se na "Least-Squares" (Metoda Najmanjih Kvadrata) algoritam za "Cold Start" inicijalizaciju pri prvom kliku.

### 3.2. DOP Optimizacija (Smart Satellite Selection)
Kako bi se sačuvali CPU resursi simulacije, ugrađen je selektor (Geometric Dilution of Precision - GDOP) koji iz mora vidljivih satelita uvijek nasumično bira najoptimalnijih 6 koji tvore "najširi" tetraedar na nebeskom svodu.

### 3.3. RAIM Algoritam (Receiver Autonomous Integrity Monitoring)
U prijemnik je ugrađen moćan sigurnosni mehanizam zasnovan na medijani (Median-Based RAIM). On analizira tzv. *Inovacije* (pre-fit residuals) svakog satelita nezavisno. Ukoliko detektira da neki satelit (poput `SAT_0_0` u testiranju) emitira kompromitirane ili hakirane podatke, algoritam ga trajno izolira i sprječava urušavanje EKF filtera.

---

## 4. Simulacija Hardvera (Satovi)

### 4.1. Allanova Varijanca
Savršen sat ne postoji. I sateliti i prijemnik koriste složen stohastički model sata baziran na Allanovoj varijanci, koji uključuje:
- **White Frequency Noise** (Kratkoročne fluktuacije)
- **Random Walk Frequency Noise** (Dugoročni drift kvarcnog oscilatora prijemnika)

### 4.2. Relativistička Korekcija
Na satelite utječu Opća i Specijalna teorija relativnosti (slabija gravitacija, ali veća brzina kretanja u odnosu na površinu Zemlje). Uključen je stacionarni relativistički drift, ali i **Dinamička Relativistička Korekcija** – ubrzanje i usporavanje sata na osnovu trenutne ekscentrične anomalije uslijed blagog mijenjanja visine orbite!

---

## 5. Astrodinamika i Fizika (Physics Engine)

### 5.1. Ekscentrične Orbite i Keplerov Solver
Sateliti ne kruže u savršenim kružnicama. Implementirane su realistične eliptične orbite ($e=0.015$). Računanje prave pozicije vrši se rješavanjem Keplerove jednadžbe kroz iterativni **Newton-Raphson** algoritam.

### 5.2. J2 Perturbacija
Zemlja nije savršena sfera, već je spljoštena na polovima (oblik geoida). `physics_engine.py` sadrži `J2` koeficijent koji simulira stvarni efekt precesije Longitude Ascending Node-a (LAN) i argumenta perigeja tijekom dužeg vremenskog perioda.

### 5.3. Atmosferski Modeli i Sagnac
- **Hopfield Model**: Precizno modelira kašnjenje radio-signala pri prolasku kroz "vlažni" (vodena para) i "suhi" sloj troposfere ovisno o elevaciji satelita.
- **Sagnac Efekt**: Zemlja se zarotira za djelić sekunde dok signal stigne od satelita do antene prijemnika. Ovaj relativistički efekt rotacijskog referentnog sustava je u potpunosti ispravljen!

---

## 6. Korisničko Sučelje i Karakteristike Vizualizacije

- **3D Real-Time Render**: PyVista/OpenGL prikaz orbita, satelita i terena s dinamičkim renderiranjem tekstualnih panela.
- **LOS Raycasting (Line of Sight)**: Proceduralno generirani planinski lanci oko površine planete fizički blokiraju radio signale! Algoritam baca matematičke zrake (raycasting) svake simulacijske sekunde; ako planina zakloni satelit, on se automatski izbacuje iz liste vidljivih.
- **Kinematic Fly Mode**: Aktiviranjem tipke `M` (Move), prijemnik prestaje biti stacionaran i kreće se poput aviona 500 metara iznad lokalnog terena. EKF uspješno prepoznaje pokret i računa Doppler-like efekte u 3D brzini.
- **Koordinatni Transformator**: Interaktivno prebacivanje (tipka `D`) između čistog Decimal-Degrees formata (ECEF interpolacija) i profesionalnog Degrees, Minutes, Seconds (D.M.S) formata navigacije.

---
**Status projekta:** *Faza 10/10 kompletirana. Spremno za integraciju.*
