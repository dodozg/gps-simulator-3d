# GPS Simulator 3D

*[🇬🇧 English version](README.en.md) · [Tehnička dokumentacija](GPS_Simulator_Documentation.md) · [Priča o Sagnac bugu](docs/sagnac-bug.md)*

Simulator satelitske navigacije u Pythonu: Walker-Delta konstelacija, eliptične
orbite (Kepler + J2), fizička obrada signala (PRN + FFT korelacija, multipath,
AWGN), dual-frequency iono-free kombinacija te navigacijski procesor s Extended
Kalman filterom i RAIM zaštitom. 3D prikaz i živa simulacija su u web kontrolnom
centru (CesiumJS + FastAPI).

Za detaljan opis algoritama vidi [`GPS_Simulator_Documentation.md`](GPS_Simulator_Documentation.md);
za priču o dijagnostici Sagnac buga (ENU dekompozicija → zero-noise test) vidi
[`docs/sagnac-bug.md`](docs/sagnac-bug.md).

## Struktura

| Modul | Uloga |
|-------|-------|
| `physics_engine.py`   | Orbite, atmosfera (iono/tropo), relativnost, modeli satova |
| `terrain.py`          | Pravi globalni DEM (NASA SRTM) + bilinearna interpolacija visina |
| `satellite.py`        | Walker-Delta konstelacija i satelitski satovi |
| `signal_processing.py`| Pravi C/A Gold kodovi, RF kanal, FFT korelacija |
| `receiver.py`         | Estimator: LS inicijalizacija + EKF + RAIM (vlasi mjerni model) |
| `utils.py`            | Geodezija: LLA ↔ ECEF na WGS-84 elipsoidu, DMS format |
| `measurement.py`      | Mjerni model: kanal + korekcije + DOP selekcija → pseudoudaljenosti |
| `web/`                | Web kontrolni centar + GPS učilište (FastAPI + CesiumJS) — 3D prikaz |
| `benchmark.py`        | Headless pokretanje scenarija i statistika greške |
| `skyplot.py`          | Headless skyplot + grafovi GDOP/greška/NIS (PNG) |
| `rtk.py`              | Carrier-phase RTK (cm-precizno, double differencing) |
| `spoofing.py`         | Spoofing/jamming lab: napadi kroz pravi EKF/RAIM (headless) |
| `iono.py`             | Klobuchar ionosferska analiza (dnevna krivulja TEC-a) |
| `multignss.py`        | Multi-GNSS (GPS/GAL/GLO/BDS) + procjena inter-system biasa |
| `scenario.py`         | Snimanje/reprodukcija scenarija (JSON) + usporedba algoritama |

Cijeli engine radi bez GUI-ja, pa se testira i mjeri na CI-ju (3D prikaz je u `web/`).

Teren je stvarni globalni DEM (`terrain_dem.npz`, izveden iz NASA SRTM RAMP2,
javna domena) — oceani na razini mora, planine na pravim mjestima. Datoteka je
uključena; `fetch_terrain.py` je regenerira/finije (`--width`).

`spoofing.py` je laboratorij napada koji se ubrizgavaju na razinu mjerenja pa
prolaze kroz pravi EKF/RAIM: **koordinirani spoof** (konzistentna lažna mjerenja
tiho odvuku poziciju — RAIM ne alarmira, temeljno ograničenje), **naivni
multi-SV** (nezavisni pomaci — robusni RAIM ih izolira), **meaconing** (uniformno
kašnjenje — upije se u sat prijemnika), **jamming** (J/N ruši broj satelita i
gubi fix). `--plot` crta grešku/RAIM/satelite kroz vrijeme.

Ionosfera je pravi **Klobuchar model** (`physics_engine.klobuchar_delay`), ovisan
o dobu dana (vrh TEC-a ~14:00 lokalno, noćni pod) i geometriji. Prijemnik injektira
kašnjenje na L1/L2 pa ga iono-free kombinacija poništava; `iono.py` crta dnevnu
krivulju i ovisnost o elevaciji.

`multignss.py` kombinira **GPS + Galileo + GLONASS + BeiDou** (`MultiGNSSConstellation`).
Svaki sustav unosi konstantni **inter-system bias** (različite vremenske skale) koji
prijemnik procjenjuje kao dodatno stanje uz položaj i vlastiti sat. Više satelita =
niži PDOP i fix i tamo gdje GPS sam vidi < 4 satelita (npr. maska 30° = urbani kanjon).

`scenario.py` sprema cijeli scenarij (lokacija/vrijeme/kvar/seed) u **JSON** pa je
reprodukcija deterministička (bajt-identične metrike). `run` odvrti scenarij,
`compare` uspoređuje algoritme (RAIM on/off) ili dva scenarija, `record` snima novi.
Bundlani primjeri su u `scenarios/` (vedro, teren, koordinirani/naivni spoof).

## Instalacija

Radi na Windowsu, macOS-u i Linuxu (engine je čisti Python; razlikuju se samo
launcheri i putanje).

- **Windows:** dvoklik **`setup.bat`** — kreira svjež `.venv` i instalira
  ovisnosti (web + alati + testovi).
- **macOS / Linux:** **`./setup.sh`** — isto. Prije toga možda `chmod +x *.sh`.

Ručno (bilo koji OS):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     |  Linux/macOS: source .venv/bin/activate

pip install -r requirements-dev.txt    # engine + testovi
pip install -r requirements-plots.txt  # + matplotlib za CLI alate (skyplot/iono/…)
pip install -r requirements-web.txt    # + web kontrolni centar (uključuje plots)
```

Launcheri (`run_*.bat` na Windowsu; `./gps.sh <alat>` na macOS/Linux) prvo probaju
venv python, a ako on ne radi padaju na sistemski Python + `PYTHONPATH` na `.venv`
pakete.

> **Napomena o `.venv` na Google Driveu:** jedan `.venv` ne može posluživati i
> Windows (`Scripts\`, `.exe`) i Mac (`bin/`) — layout je različit. `.venv` je
> gitigniran; na svakom stroju ga kreiraj nanovo (`setup.bat` / `./setup.sh`).

## Pokretanje

Na macOS/Linux svi alati idu kroz jedinstveni launcher **`./gps.sh <alat>`**
(npr. `./gps.sh benchmark --seconds 300`, `./gps.sh scenario list`). Na Windowsu
postoje ekvivalentni `run_*.bat` (dvoklik). Izravno kroz Python (bilo koji OS):

```bash
python benchmark.py     # headless: konvergencija EKF-a i statistika greške
python skyplot.py       # skyplot + GDOP/greška/NIS grafovi -> skyplot.png
python rtk.py           # carrier-phase RTK demo (cm-precizno)
python spoofing.py --attack coordinated --plot   # spoofing/jamming lab -> spoofing.png
python iono.py          # Klobuchar dnevna ionosfera -> iono.png
python multignss.py     # GPS+GAL+GLO+BDS: dostupnost/PDOP/ISB -> multignss.png
python scenario.py list                                  # bundlani JSON scenariji
python scenario.py compare scenarios/jamming_naive_spoof.json   # RAIM on vs off
pytest                  # test suite
```

Interaktivni 3D prikaz (globus, klik-postavljanje prijemnika, telemetrija, živa
simulacija) je u **web kontrolnom centru** — vidi niže i [`web/README.md`](web/README.md).

## Web kontrolni centar + GPS učilište

Moderno web sučelje (3D globus na CesiumJS, živa simulacija, telemetrija i
edukativni pojmovnik na klik, dvojezično HR/EN) koje postojeći numpy engine
koristi izravno preko FastAPI backenda. Jednom (traži Node 18+) pa pokreni:
**Windows** `build_web.bat` → `run_webapp.bat`; **macOS/Linux** `./build_web.sh`
→ `./run_webapp.sh` (ili kraće `./gps.sh web`). Detalji u
[`web/README.md`](web/README.md).

## Testovi

Testovi su u `tests/` i pokreću se s `pytest` (konfiguracija u `pyproject.toml`).
Svi izvori šuma primaju eksplicitni `np.random.Generator` koji konstelacija i
prijemnik dijele (`np.random.default_rng(seed)`), pa su rezultati reproducibilni
bez oslanjanja na globalno stanje. CI (`.github/workflows/ci.yml`) vrti suite na
Pythonu 3.11–3.13.
