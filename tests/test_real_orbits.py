"""Prave orbite (CelesTrak GP + SGP4): podaci, geometrija, rotacija Zemlje, živa sesija."""
import math

import numpy as np
import pytest

pytest.importorskip("sgp4")

import real_orbits  # noqa: E402
from utils import ecef_to_lla  # noqa: E402

EPOCH = "2026-11-20T08:00:00Z"


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    # testovi nikad ne idu na mrežu niti pišu u korisnikov cache
    monkeypatch.setenv("GPSWEB_CACHE", str(tmp_path))


@pytest.fixture(scope="module")
def con():
    gp = real_orbits.load_gp(allow_fetch=False)
    c = real_orbits.RealConstellation(EPOCH, rng=np.random.default_rng(0), gp=gp)
    c.update_all(0.0)
    return c


def test_snapshot_has_all_systems_and_unique_labels(con):
    counts = con.info(0.0)["counts"]
    assert counts["GPS"] >= 24 and counts["GAL"] >= 20 and counts["GLO"] >= 20 and counts["BDS"] >= 30
    ids = [s.sat_id for s in con.satellites]
    assert len(ids) == len(set(ids))
    assert any(i.startswith("G") and i[1:].isdigit() for i in ids)


def test_gps_orbit_geometry(con):
    gps = [s for s in con.satellites if s.system == "GPS"]
    for s in gps:
        r = np.linalg.norm(s.current_pos)
        assert 26_000e3 < r < 27_100e3            # ~26 560 km (+ ekscentricitet)
        assert 52.0 < s.i < 58.0                 # nominalno 55°, stvarni sateliti odstupaju


def test_beidou_geo_stays_over_its_slot():
    # BeiDou C04 je geostacionaran na ~160°E: dužina mora ostati ista kroz 12 h.
    # To provjerava i SGP4 i rotaciju TEME -> ECEF (GMST).
    gp = real_orbits.load_gp(allow_fetch=False)
    c = real_orbits.RealConstellation(EPOCH, gp=gp, systems=("BDS",))
    geo = next(s for s in c.satellites if s.sat_id == "C04")
    lons = []
    for t in (0.0, 6 * 3600.0, 12 * 3600.0):
        geo.update_position(t)
        lat, lon, alt = ecef_to_lla(*geo.current_pos)
        lons.append(lon)
        assert abs(lat) < 6.0 and 35_000e3 < alt < 36_500e3   # stariji GEO-i su malo nagnuti
    assert max(lons) - min(lons) < 0.5
    assert abs(lons[0] - 160.0) < 1.5


def test_velocity_matches_finite_difference(con):
    s = next(x for x in con.satellites if x.system == "GAL")
    v = s.velocity_at(100.0)
    p1, _, _ = s._state(101.0)
    p0, _, _ = s._state(99.0)
    assert np.allclose(v, (p1 - p0) / 2.0, atol=0.5)        # [m/s]
    assert 1000 < np.linalg.norm(v) < 5000                  # MEO brzina u ROTIRAJUĆEM (ECEF) okviru


def test_time_of_day_and_labels():
    assert real_orbits.sat_label("GPS BIIR-5  (PRN 22)", "GPS", 1) == "G22"
    assert real_orbits.sat_label("BEIDOU-2 G4 (C04)", "BDS", 2) == "C04"
    assert real_orbits.sat_label("GSAT0101 (GALILEO-PFM)", "GAL", 3) == "E101"
    assert real_orbits.sat_label("COSMOS 2433 (720)", "GLO", 4) == "R720"
    c = real_orbits.RealConstellation(EPOCH, systems=("GPS",), t0=500.0)
    assert c.utc_at(500.0).strftime("%H:%M:%S") == "08:00:00"
    assert c.gps_tod(500.0) == pytest.approx(8 * 3600 + 18.0)


def test_live_session_with_real_orbits():
    pytest.importorskip("fastapi")
    from web.backend.sim_session import SimSession
    from web.backend.serialize import state_frame
    s = SimSession(seed=3)
    s.set_receiver(45.815, 15.982, 120.0)
    for _ in range(3):
        s.advance(5.0)
    s.set_orbits("real", EPOCH)
    s.set_iono_tow0(0.0)                         # ignorira se: doba dana je pravo
    errs = []
    for k in range(30):
        s.advance(10.0)
        if s.calc_pos is not None and k > 5:
            errs.append(np.linalg.norm(s.calc_pos - s.gt_pos))
    assert len(errs) > 15 and np.median(errs) < 20.0
    f = state_frame(s)
    assert f["orbits"]["mode"] == "real" and f["orbits"]["utc"].startswith("2026-11-20T08:0")
    gmst = f["orbits"]["gmst_rad"]
    assert 0.0 <= gmst < 2 * math.pi
    # ionosfera u pravom GPS dobu dana (UTC + 18 s)
    assert f["tow_now"] == pytest.approx((8 * 3600 + 18.0 + (s.sim_time - 15.0)) % 86400, abs=1.0)
    s.reset()
    assert state_frame(s)["orbits"]["mode"] == "walker"
