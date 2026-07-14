"""Model visina terena — pravi globalni DEM s fallbackom na proceduralni.

Prije je teren bio čista suma sinusa (`physics_engine.calculate_terrain_elevation`)
koja je posvuda stvarala lažne planine do ~9 km i time blokirala vidljivost
satelita na stvarnim lokacijama (npr. Tokio je davao 0 vidljivih satelita).

Sada se učita stvarni DEM iz `terrain_dem.npz` (NASA SRTM RAMP2, javna domena;
vidi `fetch_terrain.py`) i visina se dobiva bilinearnom interpolacijom po
equirektangularnoj mreži. Oceani su na razini mora (0 m), planine su na pravim
mjestima s približno točnim visinama — pa LOS raycasting blokira samo stvarni
teren. Ako DEM datoteka nedostaje, koristi se gruba proceduralna zamjena koja je
uglavnom na razini mora (da ne blokira lažno).
"""
import os

import numpy as np

_DEM = None            # np.ndarray [rows, cols] int16, metri; row0=+90°, col0=-180°
_LOADED = False
_DEM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terrain_dem.npz")


def _load():
    """Lijeno učitaj DEM. Vrati polje ili None ako datoteka ne postoji."""
    global _DEM, _LOADED
    if _LOADED:
        return _DEM
    _LOADED = True
    try:
        with np.load(_DEM_PATH) as d:
            _DEM = d["elev"].astype(np.float64)
    except (FileNotFoundError, OSError, KeyError):
        _DEM = None
    return _DEM


def _procedural(lat, lon):
    """Gruba zamjena kad nema DEM-a: uglavnom razina mora, poneka blaga uzvisina.

    Namjerno niska amplituda i odsjecanje negativnog na 0 (ocean) da raycasting
    ne blokira satelite lažnim planinama kao stara sinusna verzija.
    """
    la = np.radians(lat)
    lo = np.radians(lon)
    h = (np.sin(lo * 2) * np.cos(la * 3)
         + 0.5 * np.sin(lo * 5 + 1.0) * np.cos(la * 4))
    h = np.maximum(h - 0.35, 0.0)          # najveći dio globusa -> 0 (more/nizina)
    return h * 3000.0                       # skromne planine do ~3 km


def elevation(lat, lon):
    """Visina terena [m] na (lat, lon) u stupnjevima. Bilinearno iz DEM-a."""
    dem = _load()
    if dem is None:
        return float(_procedural(float(lat), float(lon)))
    return float(_bilinear(dem, np.asarray([lat], float), np.asarray([lon], float))[0])


def elevation_array(lats, lons):
    """Vektorizirano: visine [m] za nizove lat/lon (za bojenje globusa)."""
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    dem = _load()
    if dem is None:
        return _procedural(lats, lons)
    return _bilinear(dem, lats, lons)


def _bilinear(dem, lats, lons):
    """Bilinearna interpolacija po equirektangularnoj mreži s omatanjem po dužini."""
    rows, cols = dem.shape
    # kontinuirani indeksi (row raste kako lat pada s +90 na -90)
    fr = (90.0 - lats) / 180.0 * (rows - 1)
    fc = ((lons + 180.0) % 360.0) / 360.0 * cols      # omatanje dužine

    fr = np.clip(fr, 0.0, rows - 1)
    r0 = np.floor(fr).astype(int)
    r1 = np.minimum(r0 + 1, rows - 1)
    dr = fr - r0

    c0 = np.floor(fc).astype(int) % cols
    c1 = (c0 + 1) % cols
    dc = fc - np.floor(fc)

    v00 = dem[r0, c0]; v01 = dem[r0, c1]
    v10 = dem[r1, c0]; v11 = dem[r1, c1]
    top = v00 * (1 - dc) + v01 * dc
    bot = v10 * (1 - dc) + v11 * dc
    return top * (1 - dr) + bot * dr


def has_real_dem():
    """True ako je stvarni DEM učitan (a ne proceduralna zamjena)."""
    return _load() is not None
