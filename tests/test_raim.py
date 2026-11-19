"""Statistički RAIM: chi-kvadrat razdiobe, FDE, zaštitne granice i rad u prijemniku."""
import numpy as np
import pytest

import raim
from satellite import WalkerDeltaConstellation
from receiver import Receiver
from utils import lla_to_ecef


# --- statistika (referentne vrijednosti iz scipy.stats, ovdje bez ovisnosti) ---
@pytest.mark.parametrize("p,k,ref", [
    (1e-5, 1, 19.5114), (1e-5, 4, 28.4733), (1e-5, 6, 33.1071), (1e-3, 10, 29.5883),
])
def test_chi2_isf_matches_reference(p, k, ref):
    assert raim.chi2_isf(p, k) == pytest.approx(ref, abs=1e-3)


@pytest.mark.parametrize("k,ref", [(1, 56.3611), (2, 60.9568), (4, 67.2441), (6, 72.0312)])
def test_noncentrality_matches_reference(k, ref):
    # λ za P_FA=1e-5, P_MD=1e-3
    assert raim.noncentrality(k) == pytest.approx(ref, abs=1e-3)


def test_cdf_and_sf_are_complementary():
    for k in (1, 3, 8):
        for x in (0.3, 4.0, 25.0):
            assert raim.chi2_cdf(x, k) + raim.chi2_sf(x, k) == pytest.approx(1.0, abs=1e-12)
    assert raim.ncx2_cdf(5.0, 4, 0.0) == pytest.approx(raim.chi2_cdf(5.0, 4))


# --- run_raim na sintetičkoj geometriji -------------------------------------
def _geometry(n, rng):
    pos = np.array(lla_to_ecef(45.0, 15.0, 100.0))
    up = pos / np.linalg.norm(pos)
    G = []
    for _ in range(n):
        v = rng.normal(size=3)
        v -= v.dot(up) * up
        v /= np.linalg.norm(v)
        el = rng.uniform(np.radians(15), np.radians(85))
        los = np.cos(el) * v + np.sin(el) * up          # smjer prema satelitu
        G.append(list(-los) + [1.0])                    # (prijemnik − satelit)/r, sat
    return np.array(G), pos


def test_clean_measurements_pass_and_bound_error():
    rng = np.random.default_rng(1)
    G, pos = _geometry(9, rng)
    sigma = np.full(9, 3.0)
    res = raim.run_raim(G, rng.normal(0, 3.0, 9), sigma, pos)
    assert res["status"] == "ok" and res["dof"] == 5
    assert res["test"] < res["threshold"]
    assert 0 < res["hpl"] < 200 and 0 < res["vpl"] < 300


def test_single_fault_is_detected_and_excluded():
    rng = np.random.default_rng(2)
    G, pos = _geometry(9, rng)
    y = rng.normal(0, 3.0, 9)
    y[4] += 120.0                                       # kvar na satelitu 4
    res = raim.run_raim(G, y, np.full(9, 3.0), pos)
    assert res["status"] == "excluded" and res["excluded"] == [4]


def test_no_redundancy_means_unavailable_and_dof1_cannot_exclude():
    rng = np.random.default_rng(3)
    G, pos = _geometry(4, rng)
    assert raim.run_raim(G, rng.normal(0, 3, 4), np.full(4, 3.0), pos)["status"] == "unavailable"
    G, pos = _geometry(5, rng)
    y = rng.normal(0, 3, 5)
    _, S, _, _ = raim._solve(G, y, np.full(5, 3.0))
    k = int(np.argmax(np.diag(S)))                      # satelit koji test najbolje "vidi"
    y[k] += 30 * 3.0 / np.sqrt(S[k, k])                 # 30σ u prostoru reziduala
    res = raim.run_raim(G, y, np.full(5, 3.0), pos)
    assert res["status"] == "alarm" and res["excluded"] == []   # detektirano, ne izolirano


# --- u prijemniku -----------------------------------------------------------
def _run(seconds, seed, fault_m=0.0, victim=None):
    rng = np.random.default_rng(seed)
    con = WalkerDeltaConstellation(rng=rng)
    for s in con.satellites:
        s.is_spoofed = False
    gt = np.array(lla_to_ecef(45.815, 15.982, 120.0))
    rx = Receiver(gt, rng=rng)
    out = []
    for t in range(seconds):
        con.update_all(float(t))
        rx.receive_signals(con, float(t))
        if fault_m and t >= 30:
            if victim is None and rx.received_signals:
                victim = rx.received_signals[0]["sat_id"]
            for sig in rx.received_signals:
                if sig["sat_id"] == victim:
                    sig["pseudorange"] += fault_m
        pos, _ = rx.solve_position()
        if pos is not None and t >= 10:
            out.append((float(np.linalg.norm(pos - gt)), dict(rx.integrity), rx.raim_alarm,
                        dict(rx.last_solution)))
    return out, victim


def test_receiver_clean_run_rare_exclusions_and_error_inside_hpl():
    # Bez kvara: test je kalibriran (RAIM_SIGMA_SCALE) na ~0 lažnih alarma u 5400
    # epoha. Rijetko korelator ipak da pojedinačni skok od ~7σ (npr. −20 m u jednoj
    # epohi, seed 11, t=110) — RAIM ga s pravom isključi. Dopuštamo par takvih, ali
    # samo za STVARNO velike reziduale.
    out, _ = _run(150, seed=11)
    assert len(out) > 100
    excl = [(i, sol) for _, i, alarm, sol in out if alarm]
    assert len(excl) <= 2
    for i, sol in excl:
        assert all(abs(sol[sid]["residual_m"]) > 10.0 for sid in i["excluded"])
    assert all(err < i["hpl"] for err, i, _, _ in out if i.get("hpl"))   # 3D greška < HPL


def test_receiver_detects_small_clock_fault():
    # 40 m na jednom satelitu: stari prag (600 m) to nije mogao vidjeti.
    out, victim = _run(90, seed=11, fault_m=40.0)
    after = [i for _, i, _, _ in out[25:]]
    hits = sum(victim in i.get("excluded", []) for i in after)
    used = [i for i in after if i["status"] != "unavailable"]
    assert hits >= 0.9 * len(used) > 0
