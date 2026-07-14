"""Multi-GNSS (#6): više satelita, bolji PDOP, procjena ISB-a, dostupnost."""
import numpy as np

from satellite import MultiGNSSConstellation
from multignss import run_compare


def test_constellation_has_all_systems_tagged():
    con = MultiGNSSConstellation(rng=np.random.default_rng(0))
    assert len(con.satellites) == 96                      # 4 sustava x 24
    systems = {s.system for s in con.satellites}
    assert systems == {"GPS", "GAL", "GLO", "BDS"}
    assert con.sys_bias["GPS"] == 0.0                     # GPS je referenca


def test_more_satellites_and_better_geometry():
    data = run_compare(45.815, 15.982, 120.0, mask_deg=10.0, seed=1234)
    gps_n, gps = data["gps"]
    all_n, alls = data["all"]
    assert all_n > gps_n                                  # više sustava = više satelita
    assert alls["pdop"] <= gps["pdop"]                    # bolja (ili jednaka) geometrija


def test_inter_system_bias_is_recovered():
    data = run_compare(45.815, 15.982, 120.0, mask_deg=10.0, seed=1234)
    _, alls = data["all"]
    for s, truth in data["sys_bias"].items():
        if s in alls["isb_est"]:
            assert abs(alls["isb_est"][s] - truth) < 8.0  # procijenjen unutar par metara


def test_multignss_keeps_fix_where_gps_alone_fails():
    # Visoka maska (urbani kanjon): GPS sam vidi < 4 satelita -> nema fixa,
    # ali sva četiri sustava zajedno i dalje rješavaju.
    data = run_compare(45.815, 15.982, 120.0, mask_deg=30.0, seed=1234)
    _, gps = data["gps"]
    _, alls = data["all"]
    assert gps is None                                    # GPS-only pao
    assert alls is not None and alls["pos_err"] < 200.0   # multi-GNSS drži fix


def test_availability_sweep_multignss_dominates():
    data = run_compare(45.815, 15.982, 120.0, mask_deg=10.0, seed=1234)
    sw = data["sweep"]
    assert np.all(sw["all_n"] >= sw["gps_n"])             # uvijek barem toliko satelita
    assert sw["all_n"][-1] >= 4                            # čak i na maski 45° ima fix
