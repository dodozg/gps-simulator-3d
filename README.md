# GPS Simulator 3D

Simulator satelitske navigacije u Pythonu: Walker-Delta konstelacija, eliptične
orbite (Kepler + J2), fizička obrada signala (PRN + FFT korelacija, multipath,
AWGN), dual-frequency iono-free kombinacija te navigacijski procesor s Extended
Kalman filterom i RAIM zaštitom. 3D vizualizacija radi na PyVista/VTK.

Za detaljan opis algoritama vidi [`GPS_Simulator_Documentation.md`](GPS_Simulator_Documentation.md).

## Struktura

| Modul | Uloga |
|-------|-------|
| `physics_engine.py`   | Orbite, atmosfera (iono/tropo), relativnost, modeli satova |
| `terrain.py`          | Pravi globalni DEM (NASA SRTM) + bilinearna interpolacija visina |
| `satellite.py`        | Walker-Delta konstelacija i satelitski satovi |
| `signal_processing.py`| PRN kodovi, RF kanal, FFT korelacija |
| `receiver.py`         | LS inicijalizacija + EKF + RAIM + DOP selekcija |
| `utils.py`            | Geodezija: LLA ↔ ECEF na WGS-84 elipsoidu, DMS format |
| `main.py`             | PyVista GUI (jedini dio koji treba GPU/render) |
| `benchmark.py`        | Headless pokretanje scenarija i statistika greške |
| `skyplot.py`          | Headless skyplot + grafovi GDOP/greška/NIS (PNG) |
| `rtk.py`              | Carrier-phase RTK (cm-precizno, double differencing) |
| `spoofing.py`         | Spoofing/jamming lab: napadi kroz pravi EKF/RAIM (headless) |
| `iono.py`             | Klobuchar ionosferska analiza (dnevna krivulja TEC-a) |
| `multignss.py`        | Multi-GNSS (GPS/GAL/GLO/BDS) + procjena inter-system biasa |

Engine (sve osim `main.py`) radi bez GUI-ja, pa se testira i mjeri na CI-ju.

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

## Instalacija

Na Windowsu je najlakše dvokliknuti **`setup.bat`** — kreira svjež `.venv` i
instalira sve ovisnosti (GUI + testovi). Ručno:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     |  Linux/macOS: source .venv/bin/activate

# Samo engine + testovi (bez GPU-a):
pip install -r requirements-dev.txt

# Puni GUI (3D vizualizacija):
pip install -r requirements-viz.txt
```

Launcheri (`run_simulator.bat`, `run_benchmark.bat`, `run_tests.bat`) koriste
`.venv\Scripts\python.exe`, a ako on ne radi padaju na sistemski Python +
`PYTHONPATH` na `.venv` pakete.

## Pokretanje

```bash
python main.py          # 3D simulator (na Windowsu: dvoklik run_simulator.bat)
python benchmark.py     # headless: konvergencija EKF-a i statistika greške
python skyplot.py       # skyplot + GDOP/greška/NIS grafovi -> skyplot.png
python rtk.py           # carrier-phase RTK demo (cm-precizno)
python spoofing.py --attack coordinated --plot   # spoofing/jamming lab -> spoofing.png
python iono.py          # Klobuchar dnevna ionosfera -> iono.png
python multignss.py     # GPS+GAL+GLO+BDS: dostupnost/PDOP/ISB -> multignss.png
pytest                  # test suite
```

Kontrole u 3D prikazu: **klik** na Zemlju postavlja prijemnik, **D** prebacuje
DMS format, **M** uključuje kinematički način (let), **T** prebacuje između
hipsometrijskog reljefa i stvarne satelitske teksture (NASA Blue Marble,
`earth_texture.jpg`, javna domena).

## Testovi

Testovi su u `tests/` i pokreću se s `pytest` (konfiguracija u `pyproject.toml`).
Svi izvori šuma primaju eksplicitni `np.random.Generator` koji konstelacija i
prijemnik dijele (`np.random.default_rng(seed)`), pa su rezultati reproducibilni
bez oslanjanja na globalno stanje. CI (`.github/workflows/ci.yml`) vrti suite na
Pythonu 3.11–3.13.
