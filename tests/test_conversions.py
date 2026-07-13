"""Koordinatne transformacije, orbitalna mehanika i relativnost.

Zamjenjuje raniju ad-hoc skriptu verify_logic.py pravim pytest tvrdnjama.
"""
import numpy as np
import pytest

from utils import lla_to_ecef, ecef_to_lla, format_dms, WGS84_A, WGS84_B
from physics_engine import get_orbital_period, get_relativistic_drift_rate, R_EARTH


@pytest.mark.parametrize("lat,lon,alt", [
    (0, 0, 0),          # ekvator, nulti meridijan
    (45, 45, 1000),     # nasumična točka
    (-90, 0, 0),        # južni pol
    (51.5074, -0.1278, 50),  # London
    (0, 180, 20200000), # GPS visina
])
def test_lla_ecef_roundtrip(lat, lon, alt):
    x, y, z = lla_to_ecef(lat, lon, alt)
    lat2, lon2, alt2 = ecef_to_lla(x, y, z)
    # Bowringova zatvorena formula je sub-milimetar točna.
    np.testing.assert_allclose([lat2, lon2], [lat, lon], atol=1e-9)
    assert abs(alt2 - alt) < 1e-4


def test_ellipsoid_reference_radii():
    # Na ekvatoru radijus = velika poluos; na polu = mala poluos (WGS-84).
    x_eq, _, _ = lla_to_ecef(0.0, 0.0, 0.0)
    _, _, z_pole = lla_to_ecef(90.0, 0.0, 0.0)
    assert abs(x_eq - WGS84_A) < 1e-6
    assert abs(z_pole - WGS84_B) < 1e-6
    # Spljoštenost je stvarna: polarni radijus je ~21 km manji od ekvatorskog.
    assert 21000 < (WGS84_A - WGS84_B) < 21500


def test_geodetic_differs_from_geocentric():
    # Ključna posljedica elipsoida: geodetska širina (koju vraćamo) NIJE jednaka
    # geocentričnoj (arctan z/p). Razlika je najveća oko 45° (~11.5').
    x, y, z = lla_to_ecef(45.0, 0.0, 0.0)
    geocentric = np.degrees(np.arctan2(z, np.hypot(x, y)))
    assert 45.0 - geocentric > 0.15  # geodetska je veća za >9 lučnih minuta


def test_gps_orbital_period():
    a = R_EARTH + 20200000
    period_hours = get_orbital_period(a) / 3600
    # GPS sateliti imaju period od ~11.97 h (pola zvjezdanog dana).
    assert 11.9 < period_hours < 12.1


def test_relativistic_drift_matches_gps():
    drift_micros_per_day = get_relativistic_drift_rate(R_EARTH + 20200000) * 86400 * 1e6
    # Očekivano ~38 µs/dan (45 GR − 7 SR).
    assert 35 < drift_micros_per_day < 42


def test_format_dms_hemispheres():
    assert format_dms(45.5, is_lat=True).endswith("N")
    assert format_dms(-45.5, is_lat=True).endswith("S")
    assert format_dms(15.0, is_lat=False).endswith("E")
    assert format_dms(-15.0, is_lat=False).endswith("W")
