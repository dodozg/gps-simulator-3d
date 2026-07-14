"""Pravi DEM: poznate visine i da stvarne lokacije više nisu lažno blokirane."""
import numpy as np

import terrain
from benchmark import run_scenario


def test_real_dem_is_loaded():
    assert terrain.has_real_dem(), "terrain_dem.npz mora biti prisutan (fetch_terrain.py)"


def test_known_elevations_are_physical():
    everest = terrain.elevation(27.99, 86.93)   # Himalaja
    pacific = terrain.elevation(0.0, -140.0)     # sredina Tihog oceana
    alps = terrain.elevation(46.5, 9.0)          # Alpe
    assert everest > 5000.0                       # visoka planina
    assert abs(pacific) < 200.0                    # ocean ~ razina mora
    assert alps > 1500.0
    assert everest > alps > abs(pacific)           # monotono po visini


def test_elevation_array_matches_scalar():
    lats = np.array([27.99, 0.0, 46.5, 35.68])
    lons = np.array([86.93, -140.0, 9.0, 139.69])
    vec = terrain.elevation_array(lats, lons)
    sca = np.array([terrain.elevation(la, lo) for la, lo in zip(lats, lons)])
    assert np.allclose(vec, sca, atol=1e-6)


def test_longitude_wraps_around_antimeridian():
    # -180 i +180 su ista točka -> ista visina (test omatanja u interpolaciji)
    assert abs(terrain.elevation(10.0, -180.0) - terrain.elevation(10.0, 180.0)) < 1e-6


def test_tokyo_is_no_longer_blocked():
    # Prije (sinusni teren) Tokio je davao 0 riješenih epoha; sada mora imati fix.
    errors, gdops, alarms, nis = run_scenario(35.68, 139.69, 40.0, 60, seed=1234)
    assert len(errors) > 40, "Tokio mora dobiti navigacijsko rješenje sa stvarnim terenom"
    assert np.median(errors) < 200.0


def test_procedural_fallback_is_bounded_and_nonnegative():
    # Zamjena bez DEM-a: nikad ispod mora, skromne planine (da ne blokira lažno).
    lo = np.linspace(-180, 180, 73)
    la = np.linspace(-80, 80, 33)
    LO, LA = np.meshgrid(lo, la)
    h = terrain._procedural(LA, LO)
    assert h.min() >= 0.0
    assert h.max() < 4000.0
