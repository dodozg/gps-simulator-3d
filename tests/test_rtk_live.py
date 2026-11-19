"""Živi carrier-phase RTK u web simulaciji (rtk.LiveRTK kroz SimSession).

Provjerava: FIX s cm greškom na statičnom roveru, ispravnost cijelih brojeva
(prema simuliranoj istini), `rtk` blok u frameu (samo kad je uključen),
premještanje rovera / reset / gašenje satelita, kinematiku i dugu bazu.
"""
import itertools
import json

import numpy as np
import pytest

from rtk import lambda_ils
from web.backend.sim_session import SimSession
from web.backend.serialize import state_frame
from web.backend.routes_sim import _apply

LAT, LON = 45.815, 15.982          # Zagreb


def _fixed_ints_correct(s):
    """Jesu li svi trenutno fiksirani DD cijeli brojevi jednaki simuliranoj istini."""
    f = s.rtk.filter
    truth = s.rtk.obs_sim.true_sd_int
    return all(z == truth(b) - truth(a) for a, b, z in f.fixed_pairs)


def _run_until_fixed(s, dt, max_epochs):
    for _ in range(max_epochs):
        s.advance(dt)
        if s.rtk.filter.status == "fixed":
            return True
    return False


def test_lambda_matches_brute_force():
    # LAMBDA (dekorelacija + pretraga) mora naći ILS minimum (provjera grubom silom
    # u susjedstvu) i normu (a-z)ᵀQ⁻¹(a-z) konzistentnu s originalnim prostorom.
    rng = np.random.default_rng(3)
    n = 5
    for _ in range(30):
        A = rng.normal(size=(n, n))
        Q = (A @ A.T + np.ones((n, n)) * 5.0) * 0.05      # jako korelirana
        a = rng.integers(-50, 50, n) + np.linalg.cholesky(Q) @ rng.normal(size=n)
        cands, norms, p_boot = lambda_ils(a, Q)
        Qi = np.linalg.inv(Q)
        q = lambda z: float((a - z) @ Qi @ (a - z))         # noqa: E731
        assert abs(q(cands[0]) - norms[0]) < 1e-6 * max(1.0, norms[0])
        assert norms[0] <= norms[1] + 1e-12
        best = min(q(cands[0] + np.array(d)) for d in itertools.product([-1, 0, 1], repeat=n))
        assert best >= norms[0] - 1e-9
        assert 0.0 <= p_boot <= 1.0


def test_static_rover_reaches_fix_cm_level():
    # Zadana sesija (samo GPS, L1): statički rover, automatska baza ~4 km.
    s = SimSession(seed=1234)
    s.set_receiver(LAT, LON)
    s.set_rtk(True)
    assert _run_until_fixed(s, 10.0, 90), "RTK nije dosegao FIX u 900 s sim-vremena"
    for _ in range(5):                                  # FIX se drži (fix-and-hold)
        s.advance(10.0)
    f = state_frame(s)["rtk"]
    assert f["status"] == "fixed"
    assert _fixed_ints_correct(s)
    assert f["error_m"] < 0.05                          # centimetarski (kod: metri)
    assert f["time_to_fix_s"] is not None and 0 < f["time_to_fix_s"] <= 900
    assert 3000 < f["baseline_m"] < 5000
    assert f["n_dd"] >= 4 and f["n_fixed"] >= 4
    assert f["base"]["auto"] is True
    # RTK je znatno točniji od kodnog EKF rješenja iste epohe
    assert f["error_m"] < state_frame(s)["receiver"]["error_m"]


def test_frame_has_rtk_block_only_when_enabled():
    s = SimSession(seed=5)
    s.set_receiver(LAT, LON)
    s.advance(5.0)
    assert "rtk" not in state_frame(s)                 # zadano isključen
    _apply(s, {"type": "rtk", "on": True})
    s.advance(5.0)
    f = state_frame(s)
    assert "rtk" in f
    blk = f["rtk"]
    for k in ("status", "base", "baseline_m", "n_dd", "n_fixed", "error_m",
              "time_to_fix_s", "position", "cost_ms", "epochs"):
        assert k in blk
    assert blk["status"] in ("none", "float", "fixed")
    assert blk["position"] is not None and len(blk["position"]["ecef"]) == 3
    json.dumps(f, allow_nan=False)                      # čisti JSON (nema nan/inf)
    # postojeći ključevi frame-a ostaju
    for k in ("sim_time", "receiver", "satellites", "systems", "attack_overlay"):
        assert k in f
    _apply(s, {"type": "rtk", "on": False})
    s.advance(5.0)
    assert "rtk" not in state_frame(s)


def test_relocation_and_reset_restart_rtk():
    s = SimSession(seed=7)
    for sy in ("GAL", "BDS"):
        s.set_system_enabled(sy, True)                  # više satelita -> brz FIX
    s.set_receiver(LAT, LON)
    s.set_rtk(True)
    assert _run_until_fixed(s, 10.0, 15)
    old_base = state_frame(s)["rtk"]["base"]["ecef"]

    # premještanje rovera: nove neodređenosti, TTF ispočetka, auto baza ide za njim
    _apply(s, {"type": "set_receiver", "lat": 48.2, "lon": 16.37})
    f = state_frame(s)["rtk"]
    assert f["status"] == "none" and f["epochs"] == 0 and f["time_to_fix_s"] is None
    assert np.linalg.norm(np.subtract(f["base"]["ecef"], old_base)) > 100e3
    s.advance(10.0)
    f = state_frame(s)["rtk"]
    assert f["status"] == "float" and 3000 < f["baseline_m"] < 5000

    # Poništi: sesija na zadano -> RTK isključen
    _apply(s, {"type": "reset"})
    assert "rtk" not in state_frame(s)


def test_user_base_and_back_to_auto():
    s = SimSession(seed=11)
    s.set_receiver(LAT, LON)
    s.set_rtk(True)
    # ručna baza ~8 km sjeverno
    _apply(s, {"type": "set_base", "lat": LAT + 0.072, "lon": LON})
    s.advance(5.0)
    f = state_frame(s)["rtk"]
    assert f["base"]["auto"] is False
    assert 7500 < f["baseline_m"] < 8600
    assert abs(f["base"]["lla"]["lat"] - (LAT + 0.072)) < 1e-6
    # klijent pri ponovnom spajanju ponovno šalje istu bazu i "rtk on": bez reseta
    _apply(s, {"type": "set_base", "lat": LAT + 0.072, "lon": LON})
    _apply(s, {"type": "rtk", "on": True})
    assert state_frame(s)["rtk"]["epochs"] == f["epochs"] > 0
    # premještanje rovera NE miče ručnu bazu
    _apply(s, {"type": "set_receiver", "lat": LAT, "lon": LON + 0.01})
    assert abs(state_frame(s)["rtk"]["base"]["lla"]["lat"] - (LAT + 0.072)) < 1e-6
    # natrag na automatsku
    _apply(s, {"type": "set_base", "auto": True})
    s.advance(5.0)
    f = state_frame(s)["rtk"]
    assert f["base"]["auto"] is True and 3000 < f["baseline_m"] < 5000


def test_satellites_toggled_off():
    s = SimSession(seed=13)
    for sy in ("GAL", "BDS"):
        s.set_system_enabled(sy, True)
    s.set_receiver(LAT, LON)
    s.set_rtk(True)
    assert _run_until_fixed(s, 10.0, 15)
    n0 = s.rtk.n_common
    # ugasi referentni satelit GPS grupe i još jedan -> stanje se prilagodi, bez pada
    ref = s.rtk.filter.fixed_pairs[0][0]
    other = next(b for a, b, _ in s.rtk.filter.fixed_pairs if a == ref)
    s.set_sat_enabled(ref, False)
    s.set_sat_enabled(other, False)
    s.advance(10.0)
    f = state_frame(s)["rtk"]
    assert s.rtk.n_common <= n0 - 2
    assert f["status"] in ("float", "fixed")
    if f["status"] == "fixed":
        assert _fixed_ints_correct(s) and f["error_m"] < 0.05
    # ugasi sve sustave -> nema RTK rješenja, ali frame je ispravan
    for sy in ("GPS", "GAL", "BDS"):
        s.set_system_enabled(sy, False)
    s.advance(10.0)
    f = state_frame(s)
    assert f["rtk"]["status"] == "none" and f["rtk"]["position"] is None
    json.dumps(f, allow_nan=False)


def test_kinematic_multignss_fix_and_base_switch():
    # Kinematika (~112 m/s, 500 m iznad terena) uz GPS+Galileo+BeiDou: FIX unutar
    # par desetaka sekundi; kad se rover udalji >20 km, auto baza se prebaci.
    s = SimSession(seed=0)
    for sy in ("GAL", "BDS"):
        s.set_system_enabled(sy, True)
    s.set_receiver(LAT, LON)
    s.set_kinematic(True)
    s.set_rtk(True)
    assert _run_until_fixed(s, 5.0, 12), "kinematički RTK bez FIX-a"
    f = state_frame(s)["rtk"]
    assert _fixed_ints_correct(s) and f["error_m"] < 0.05
    for _ in range(25):                                 # 125 s -> ~14 km leta
        s.advance(5.0)
        if s.rtk.filter.status == "fixed":
            assert _fixed_ints_correct(s)
    # nastavi do prebacivanja baze (baseline > 20 km)
    for _ in range(40):
        s.advance(5.0)
        if s.rtk.base_switches:
            break
    f = state_frame(s)["rtk"]
    assert f["base_switches"] >= 1 and f["baseline_m"] < 6000


@pytest.mark.parametrize("dist_deg", [0.6])
def test_long_user_baseline_never_false_fix(dist_deg):
    # Duga baza (~65 km): rezidualna atmosfera (1 ppm) čini fiksiranje nepouzdanim.
    # Filtar to zna (donja granica nesigurnosti), pa NE smije prijaviti krivi FIX.
    s = SimSession(seed=21)
    for sy in ("GAL", "BDS"):
        s.set_system_enabled(sy, True)
    s.set_receiver(LAT, LON)
    s.set_rtk(True)
    s.set_base(LAT + dist_deg, LON)
    for _ in range(15):
        s.advance(10.0)
        if s.rtk.filter.status == "fixed":
            assert _fixed_ints_correct(s)
    f = state_frame(s)["rtk"]
    assert f["baseline_m"] > 60e3
    assert f["status"] in ("float", "fixed")
