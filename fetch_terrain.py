"""Preuzmi pravi globalni DEM (digitalni model visina) i spremi ga kompaktno.

Izvor: NASA SRTM RAMP2 "heightmap of Earth's surface" (javna domena, NASA),
equirektangularna projekcija 2:1, grayscale gdje je svjetlije = više. Razina mora
je fiksirana na vrijednost ~12 (#0c0c0c). Skidamo umanjeni thumbnail s Wikimedia
Commonsa i pretvaramo sivu skalu u metre pa spremimo kao `terrain_dem.npz`
(int16 polje visina). Runtime (`terrain.py`) samo učita to polje — bez mreže.

Ovo NIJE geodetski precizan DEM nego stvarna, ali gruba karta (piksel ~30 km na
1280×640): geografija je prava (kontinenti, oceani, planinski lanci na pravim
mjestima), a visine su približne (linearna rampa po segmentu oko razine mora).

Pokretanje (jednom, treba internet):
    python fetch_terrain.py                 # 1280×640 (default)
    python fetch_terrain.py --width 2560    # finije (ako Wikimedia dopušta)
"""
import argparse
import io
import urllib.request

import numpy as np
from PIL import Image

# Wikimedia dopušta samo određene širine thumbnailova; ove su sigurne.
_ALLOWED_WIDTHS = (640, 800, 1024, 1280, 2560)
_THUMB = ("https://upload.wikimedia.org/wikipedia/commons/thumb/1/15/"
          "Srtm_ramp2.world.21600x10800.jpg/%dpx-Srtm_ramp2.world.21600x10800.jpg")
_UA = "GPS_Simulator_3D/1.0 (educational heightmap fetch)"

# Sivu skalu (0..255) pretvaramo u metre po fizičkim sidrima izvora:
SEA_LEVEL_VALUE = 12.0     # #0c0c0c = razina mora (0 m)
LAND_M_PER_UNIT = 46.8     # kopno: ~ Everest (v≈201) -> ~8850 m
OCEAN_M_PER_UNIT = 900.0   # ocean: v=0 -> ~ -10800 m (dubokomorski jarci)


def _grayscale_to_meters(g):
    """Piecewise-linearna siva->metri karta oko razine mora (v=12)."""
    d = g.astype(np.float64) - SEA_LEVEL_VALUE
    elev = np.where(d >= 0.0, d * LAND_M_PER_UNIT, d * OCEAN_M_PER_UNIT)
    return np.round(elev).astype(np.int16)


def fetch(width=1280, out="terrain_dem.npz"):
    if width not in _ALLOWED_WIDTHS:
        width = min(_ALLOWED_WIDTHS, key=lambda w: abs(w - width))
        print(f"[i] tražena širina nije dopuštena; koristim {width}px")
    url = _THUMB % width
    print(f"[i] skidam {url}")
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    data = urllib.request.urlopen(req, timeout=60).read()
    im = Image.open(io.BytesIO(data)).convert("L")
    g = np.asarray(im)                       # [rows, cols], row 0 = +90°, col 0 = -180°
    elev = _grayscale_to_meters(g)
    np.savez_compressed(
        out, elev=elev,
        lat0=90.0, lat1=-90.0, lon0=-180.0, lon1=180.0,
        source="NASA SRTM RAMP2 (public domain), via Wikimedia Commons",
    )
    print(f"[OK] {out}: {elev.shape[0]}x{elev.shape[1]}  "
          f"min={elev.min()} m  max={elev.max()} m  "
          f"(~{360.0/elev.shape[1]:.2f} deg/px)")


def main():
    p = argparse.ArgumentParser(description="Preuzmi i spremi pravi globalni DEM.")
    p.add_argument("--width", type=int, default=1280,
                   help=f"širina thumbnaila (dopušteno: {_ALLOWED_WIDTHS})")
    p.add_argument("--out", default="terrain_dem.npz")
    args = p.parse_args()
    fetch(args.width, args.out)


if __name__ == "__main__":
    main()
