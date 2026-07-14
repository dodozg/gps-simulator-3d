"""Klobuchar ionosfera (#7): ovisnost o dobu dana, elevaciji, iono-free poništavanje."""
import numpy as np

from physics_engine import klobuchar_delay, calculate_ionospheric_delay, C, F_L1
from iono import zenith_delay_m, slant_delay_m, iono_free_residual_m, diurnal

LAT, LON = 45.815, 15.982


def test_daytime_exceeds_nighttime():
    hours, dz = diurnal(LAT, LON)
    day = dz[np.argmin(np.abs(hours - 14))]     # ~14:00 lokalno = vrh
    night = dz[np.argmin(np.abs(hours - 2))]     # ~02:00 = pod
    assert day > 1.8 * night


def test_night_floor_is_small_positive():
    hours, dz = diurnal(LAT, LON)
    night = dz[np.argmin(np.abs(hours - 3))]
    assert 0.5 < night < 2.5                      # ~ F*5e-9*c na zenitu


def test_slant_grows_toward_horizon():
    tow = 50400.0
    hi = slant_delay_m(LAT, LON, np.radians(80), 0.0, tow)
    lo = slant_delay_m(LAT, LON, np.radians(10), 0.0, tow)
    assert lo > hi                                 # obliquity: niža elevacija = duži put


def test_dual_frequency_cancels_ionosphere():
    r = abs(iono_free_residual_m(LAT, LON, np.radians(25), 0.7, 50400.0))
    assert r < 1e-6                                # iono-free rezidual ~ 0


def test_klobuchar_seconds_positive_and_bounded():
    s = klobuchar_delay(LAT, LON, np.radians(30), 0.0, 50400.0)
    assert s > 0
    assert C * s < 60.0                            # razumna magnituda [m]


def test_default_call_uses_simple_model():
    # Bez gps_tow_s -> stari konstantni model (kompatibilnost), nezavisno o dobu dana.
    sat = np.array([20200000.0 + 6371000.0, 0.0, 0.0])
    rec = np.array([6371000.0, 0.0, 0.0])
    d = calculate_ionospheric_delay(sat, rec, F_L1)
    assert 6.0 < d < 8.0                            # ~7 m zenit
