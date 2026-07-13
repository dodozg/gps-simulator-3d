"""Carrier-phase RTK: fiksno rješenje mora biti centimetarsko."""
import numpy as np

from rtk import rtk_solve


def test_rtk_fixed_is_centimeter_level():
    lat, lon = 45.815, 15.982
    dlon = 5000.0 / (6378137.0 * np.cos(np.radians(lat))) * 180.0 / np.pi  # ~5 km istočno
    res = rtk_solve((lat, lon, 120.0), (lat, lon + dlon, 120.0),
                    n_epochs=40, dt_epoch=30.0, seed=0)
    assert res is not None
    assert res["ar_success"]                 # cijeli brojevi razriješeni
    assert res["fixed_err_m"] < 0.10         # centimetarski (kod je ~desetci m)
    assert res["fixed_err_m"] <= res["float_err_m"] + 1e-6
    assert res["baseline_m"] > 3000.0        # kratka baza, par km
