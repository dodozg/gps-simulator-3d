# GPS Simulator 3D

Simulator satelitske navigacije u Pythonu: Walker-Delta konstelacija, eliptične
orbite (Kepler + J2), fizička obrada signala (PRN + FFT korelacija, multipath,
AWGN), dual-frequency iono-free kombinacija te navigacijski procesor s Extended
Kalman filterom i RAIM zaštitom. 3D vizualizacija radi na PyVista/VTK.

Za detaljan opis algoritama vidi [`GPS_Simulator_Documentation.md`](GPS_Simulator_Documentation.md).

## Struktura

| Modul | Uloga |
|-------|-------|
| `physics_engine.py`   | Orbite, atmosfera (iono/tropo), relativnost, modeli satova, teren |
| `satellite.py`        | Walker-Delta konstelacija i satelitski satovi |
| `signal_processing.py`| PRN kodovi, RF kanal, FFT korelacija |
| `receiver.py`         | LS inicijalizacija + EKF + RAIM + DOP selekcija |
| `utils.py`            | Geodezija: LLA ↔ ECEF na WGS-84 elipsoidu, DMS format |
| `main.py`             | PyVista GUI (jedini dio koji treba GPU/render) |
| `benchmark.py`        | Headless pokretanje scenarija i statistika greške |

Engine (sve osim `main.py`) radi bez GUI-ja, pa se testira i mjeri na CI-ju.

## Instalacija

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     |  Linux/macOS: source .venv/bin/activate

# Samo engine + testovi (bez GPU-a):
pip install -r requirements-dev.txt

# Puni GUI (3D vizualizacija):
pip install -r requirements-viz.txt
```

## Pokretanje

```bash
python main.py          # 3D simulator (na Windowsu: dvoklik run_simulator.bat)
python benchmark.py     # headless: konvergencija EKF-a i statistika greške
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
