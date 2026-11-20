"""Pravi GNSS podaci: RINEX parseri, broadcast efemeride, SPP i BroadcastConstellation.

Podaci (tests/data, vidi README.md tamo): RTKLIB test data (BSD-2) —
  * 07590920.05o/.05n  GSI GEONET stanica 0759 (Trimble 5700), 2005-04-02 00:00–01:00 GPST
  * brdc1820_trim.10n + igs15904_trim.sp3  IGS broadcast i IGS final precizne
    orbite za 2010-07-01 (NEOVISNA referenca za provjeru ephemeris.py).
"""
import copy
import dataclasses
import os

import numpy as np
import pytest

import ephemeris as ep
import realdata
import rinex
from broadcast_constellation import BroadcastConstellation
from receiver import Receiver

DATA = os.path.join(os.path.dirname(__file__), "data")
OBS = os.path.join(DATA, "07590920.05o")
NAV = os.path.join(DATA, "07590920.05n")
BRDC = os.path.join(DATA, "brdc1820_trim.10n")
SP3 = os.path.join(DATA, "igs15904_trim.sp3")


@pytest.fixture(scope="module")
def obs():
    return rinex.read_obs(OBS)


@pytest.fixture(scope="module")
def nav():
    return rinex.read_nav(NAV)


@pytest.fixture(scope="module")
def spp(obs, nav):
    return realdata.process(obs, nav)


# ----------------------------------------------------------------- parseri ---
def test_obs_v2_sample(obs):
    h = obs.header
    assert h.version == pytest.approx(2.10)
    assert h.marker_name == "0759" and h.receiver_type == "TRIMBLE 5700"
    np.testing.assert_allclose(h.approx_pos, [-3976219.5082, 3382372.5671, 3652512.9849])
    assert h.obs_types["*"] == ["L1", "C1", "L2", "P2"]
    assert h.interval == 30.0
    # 120 epoha (1 h @ 30 s); event zapisi (flag 4, "RINEX FILE SPLICE") preskočeni
    assert len(obs.epochs) == 120 and {e.flag for e in obs.epochs} == {0}
    e0 = obs.epochs[0]
    assert e0.t == rinex.gps_seconds(2005, 4, 2) == h.time_first_obs
    assert e0.week_tow == (1316, 518400.0)        # subota 00:00 GPST
    assert sorted(e0.obs) == ["G03", "G07", "G08", "G11", "G19", "G20", "G24", "G28"]
    assert e0.obs["G03"] == {"L1": 55923622.160, "C1": 24767686.375,
                             "L2": 43647388.242, "P2": 24767684.822}
    assert e0.lli["G03"] == {"L2": 4, "P2": 4}     # LLI 4 = pod anti-spoofingom (RINEX 2)
    l1 = obs.gps_l1(e0)
    assert l1["G03"] == {"C1": 24767686.375, "L1": 55923622.160}
    assert obs.epochs[-1].t - e0.t == pytest.approx(3570.005)


def test_nav_v2_sample(nav):
    h = nav.header
    assert h.iono_alpha == pytest.approx((1.118e-8, 1.49e-8, -5.96e-8, -5.96e-8))
    assert h.iono_beta == pytest.approx((8.806e4, 1.638e4, -1.966e5, -1.311e5))
    assert h.leap_seconds == 13
    assert len(nav.all()) == 162
    g1 = nav.ephemerides["G01"][0]
    assert g1.week == 1316 and g1.toe_sow == 525600.0 and g1.health == 0
    assert g1.sqrt_a == pytest.approx(5153.63647842)
    assert g1.af0 == pytest.approx(3.96659597754e-4)
    assert g1.tgd == pytest.approx(-3.25962901115e-9)
    assert g1.toc == rinex.gps_seconds(2005, 4, 2, 2, 0, 0) == g1.toe
    assert g1.fit_interval == 0.0                  # izostavljeno polje -> 0 (= 4 h)


V3_OBS = """\
     3.03           OBSERVATION DATA    M                   RINEX VERSION / TYPE
TEST                                                        MARKER NAME
 -3976219.5082  3382372.5671  3652512.9849                  APPROX POSITION XYZ
        0.0000        0.0000        0.0000                  ANTENNA: DELTA H/E/N
G    4 C1C L1C S1C C2W                                      SYS / # / OBS TYPES
E    2 C1C L1C                                              SYS / # / OBS TYPES
  2005     4     2     0     0    0.0000000     GPS         TIME OF FIRST OBS
                                                            END OF HEADER
> 2005 04 02 00 00  0.0000000  0  3
G03  24767686.375    55923622.160 7        45.250    24767684.822
E11  23000000.000    12345678.901
G07  24361933.475     -691177.89816                  24361930.599
>                              4  1
SPLICE                                                      COMMENT
> 2005 04 02 00 00 30.0000000  0  1
G03  24795930.671    56072048.441
"""

V3_NAV = """\
     3.03           N: GNSS NAV DATA    M: MIXED            RINEX VERSION / TYPE
GPSA   1.1180E-08  1.4900E-08 -5.9600E-08 -5.9600E-08       IONOSPHERIC CORR
GPSB   8.8060E+04  1.6380E+04 -1.9660E+05 -1.3110E+05       IONOSPHERIC CORR
    13                                                      LEAP SECONDS
                                                            END OF HEADER
R05 2005 04 02 00 15 00-1.200000000000E-05 0.000000000000E+00 3.456000000000E+05
     1.000000000000E+04-1.500000000000E+00 0.000000000000E+00 0.000000000000E+00
     2.000000000000E+04-1.500000000000E+00 0.000000000000E+00 0.000000000000E+00
     3.000000000000E+04-1.500000000000E+00 0.000000000000E+00 0.000000000000E+00
G01 2005 04 02 02 00 00 3.966595977540E-04 1.705302565820E-12 0.000000000000E+00
     1.400000000000E+02-5.218750000000E+01 4.026596389650E-09 2.871534990340E+00
    -2.676621079440E-06 5.957618006510E-03 4.174187779430E-06 5.153636478420E+03
     5.256000000000E+05 1.061707735060E-07-2.493184817740E+00-9.313225746150E-08
     9.833919144490E-01 3.093750000000E+02-1.650496813270E+00-7.889971342930E-09
    -8.571785642400E-12 1.000000000000E+00 1.316000000000E+03 0.000000000000E+00
     1.000000000000E+00 0.000000000000E+00-3.259629011150E-09 3.960000000000E+02
     5.195760000000E+05
E11 2005 04 02 02 00 00 1.000000000000E-04 0.000000000000E+00 0.000000000000E+00
     1.000000000000E+00 2.000000000000E+00 3.000000000000E+00 4.000000000000E+00
     1.000000000000E+00 2.000000000000E+00 3.000000000000E+00 4.000000000000E+00
     1.000000000000E+00 2.000000000000E+00 3.000000000000E+00 4.000000000000E+00
     1.000000000000E+00 2.000000000000E+00 3.000000000000E+00 4.000000000000E+00
     1.000000000000E+00 2.000000000000E+00 3.000000000000E+00 4.000000000000E+00
     1.000000000000E+00 2.000000000000E+00 3.000000000000E+00 4.000000000000E+00
     1.000000000000E+00 2.000000000000E+00 3.000000000000E+00 4.000000000000E+00
"""


def test_obs_v3_parser():
    o = rinex.read_obs(V3_OBS)
    assert o.header.version == pytest.approx(3.03)
    assert o.header.obs_types == {"G": ["C1C", "L1C", "S1C", "C2W"], "E": ["C1C", "L1C"]}
    assert len(o.epochs) == 2                      # event zapis (flag 4) preskočen
    e0 = o.epochs[0]
    assert e0.t == rinex.gps_seconds(2005, 4, 2)
    assert e0.obs["G07"] == {"C1C": 24361933.475, "L1C": -691177.898, "C2W": 24361930.599}
    assert e0.lli["G07"] == {"L1C": 1} and e0.ssi["G07"] == {"L1C": 6}
    l1 = o.gps_l1(e0)
    assert set(l1) == {"G03", "G07"}               # E11 nije GPS
    assert l1["G03"] == {"C1": 24767686.375, "L1": 55923622.160, "S1": 45.25}
    assert "S1" not in l1["G07"]                   # prazno polje
    assert o.gps_l1(e0, system="E")["E11"]["C1"] == 23000000.0
    assert o.epochs[1].t - e0.t == 30.0


def test_nav_v3_matches_v2(nav):
    n3 = rinex.read_nav(V3_NAV)
    assert set(n3.ephemerides) == {"G01"}          # GLONASS (3 linije) i Galileo (7) preskočeni
    assert n3.header.iono_alpha == pytest.approx(nav.header.iono_alpha)
    assert n3.header.iono_beta == pytest.approx(nav.header.iono_beta)
    e3, e2 = n3.ephemerides["G01"][0], nav.ephemerides["G01"][0]
    assert e3 == e2
    t = e2.toe + 1234.5
    np.testing.assert_array_equal(ep.sat_position(e3, t)[0], ep.sat_position(e2, t)[0])


# --------------------------------------------------------------- efemeride ---
def test_ephemeris_vs_igs_precise_orbit():
    """Neovisna referenca: IGS final SP3 orbite (kombinacija analitičkih centara,
    ~2.5 cm točnost) za isti dan kao IGS broadcast datoteka. Broadcast orbite su
    točne ~1 m (URE), a SP3 se odnosi na centar MASE (broadcast na faznu točku
    antene, razlika do ~1–2.5 m ovisno o bloku satelita) — pa očekujemo slaganje
    na razini nekoliko metara. Greška formule (npr. krivi Ω ili Δn) dala bi km."""
    brdc = rinex.read_nav(BRDC)
    sp3 = rinex.read_sp3(SP3)
    assert len(sp3) >= 29 and all(len(v) == 13 for v in sp3.values() if v)
    d_pos, d_clk = [], []
    for sat, recs in sp3.items():
        for t, xyz, clk in recs:
            eph = ep.select_ephemeris(brdc.ephemerides.get(sat, []), t)
            if eph is None:
                continue
            p, _ = ep.sat_position(eph, t)
            d_pos.append(np.linalg.norm(p - xyz))
            if np.isfinite(clk):     # IGS satovi su BEZ periodičkog relativističkog člana
                d_clk.append(ep.sat_clock(eph, t, include_relativity=False) - clk)
    d_pos = np.array(d_pos)
    d_clk = np.array(d_clk) * ep.C_LIGHT
    assert len(d_pos) > 300
    assert np.median(d_pos) < 2.5 and np.percentile(d_pos, 95) < 4.5 and d_pos.max() < 8.0
    # sat: zajednički pomak (IGST vs GPST) je dopušten; raspršenje ~1 m
    assert np.std(d_clk) < 2.0 and np.max(np.abs(d_clk - np.median(d_clk))) < 6.0


def test_ephemeris_basic_physics(nav):
    eph = nav.ephemerides["G01"][0]
    for dt in (-7200.0, 0.0, 3600.0, 7200.0):
        p, E = ep.sat_position(eph, eph.toe + dt)
        r = np.linalg.norm(p)
        assert 2.6e7 * (1 - eph.e) - 2e4 < r < 2.66e7 * (1 + eph.e) + 2e4
    v = ep.sat_velocity(eph, eph.toe)
    assert 2500 < np.linalg.norm(v) < 4500         # ECEF brzina GPS satelita ~3–4 km/s
    # relativistički član: |Δt_r| <= |F|·e·√A (~ desetke ns za e ~ 0.006)
    bound = abs(ep.F_REL) * eph.e * eph.sqrt_a
    assert abs(ep.relativistic_correction(eph, eph.toe)) <= bound + 1e-15
    # L1 TGD: oduzima se samo na zahtjev
    t = eph.toc + 100.0
    assert ep.sat_clock(eph, t, l1_tgd=True) == pytest.approx(ep.sat_clock(eph, t) - eph.tgd)
    assert ep._wrap_tk(400000.0) == 400000.0 - 604800.0
    assert ep._wrap_tk(-400000.0) == -400000.0 + 604800.0


def test_select_ephemeris(nav):
    lst = nav.ephemerides["G01"]
    assert len(lst) >= 3
    t = lst[1].toe + 1000.0
    assert ep.select_ephemeris(lst, t) is lst[1]
    assert ep.select_ephemeris(lst, lst[0].toe - 7300.0) is None       # izvan ±2 h
    sick = [dataclasses.replace(e, health=1) for e in lst]
    assert ep.select_ephemeris(sick, t) is None
    assert ep.select_ephemeris(sick, t, healthy_only=False).toe == lst[1].toe


# --------------------------------------------------------------------- SPP ---
def test_spp_accuracy_on_sample(spp):
    """SPP (L1 C/A, Klobuchar + Saastamoinen) kroz Receiver EKF na pravim podacima.

    Izmjereno na uzorku: horizontalno medijan ~0.4 m / 95% ~0.8 m, vertikalno
    medijan ~0.4 m / 95% ~2.2 m (geodetski prijemnik, mirna ionosfera, 1 h).
    Pragovi ostavljaju rezervu, ali bi uhvatili grešku modela (metri–desetke m)."""
    s = spp["summary"]
    assert spp["solved"] == spp["n_epochs"] == 120
    assert s["h_median"] < 1.5 and s["h_p95"] < 2.5
    assert s["v_median"] < 2.0 and s["v_p95"] < 4.0
    assert not spp["raim_alarms"]                  # čisti podaci -> nema lažnih alarma
    assert all(r["nsat"] >= 6 for r in spp["rows"])
    # EKF i snapshot LS daju konzistentna rješenja
    assert abs(spp["ls_summary"]["h_median"] - s["h_median"]) < 0.5


def test_atmospheric_corrections_matter(obs, nav, spp):
    raw = realdata.process(obs, nav, iono=False, tropo=False, solver="ls")
    assert raw["summary"]["v_median"] > 5.0        # bez korekcija: ~14 m vertikalno
    assert spp["summary"]["v_median"] < raw["summary"]["v_median"] / 3


def test_earth_rotation_not_double_counted(obs, nav):
    """Receiver dodaje Sagnac član sam; ako bismo i ovdje rotirali poziciju
    satelita za ω_E·τ, rotacija bi bila uračunata dvaput -> pomak od ~desetak m."""
    truth = realdata.reference_position(obs)
    good, double = [], []
    for e in obs.epochs[:20]:
        meas = realdata.build_measurements(obs, e, nav, truth, truth=truth)
        sol = realdata.solve_ls(meas, x0=truth)
        good.append(np.linalg.norm(sol["pos"] - truth))
        rot = []
        for m in meas:
            tau = np.linalg.norm(m["sat_pos"] - truth) / ep.C_LIGHT
            a = ep.OMEGA_E_GPS * tau
            R = np.array([[np.cos(a), np.sin(a), 0], [-np.sin(a), np.cos(a), 0], [0, 0, 1]])
            p = R @ m["sat_pos"]
            rot.append({**m, "sat_pos": p, "broadcast_pos": p})
        double.append(np.linalg.norm(realdata.solve_ls(rot, x0=truth)["pos"] - truth))
    assert np.median(good) < 2.0
    assert np.median(double) > 10.0


def test_clock_jump_is_handled(obs, nav):
    """Skok sata prijemnika od 1 ms (300 km u svim pseudoudaljenostima) usred niza."""
    o = copy.deepcopy(obs)
    o.epochs = o.epochs[:30]
    for e in o.epochs[15:]:
        for v in e.obs.values():
            v["C1"] += 1e-3 * ep.C_LIGHT
    res = realdata.process(o, nav)
    assert res["solved"] == 30
    assert res["summary"]["h_p95"] < 3.0 and res["summary"]["v_p95"] < 5.0


def test_cli_and_plot(tmp_path, capsys):
    pytest.importorskip("matplotlib")
    out = tmp_path / "rd.png"
    res = realdata.main([OBS, NAV, "--quiet", "--max-epochs", "10", "--plot", str(out)])
    assert res["solved"] == 10 and out.exists() and out.stat().st_size > 5000
    txt = capsys.readouterr().out
    assert "horizontalno medijan" in txt


# --------------------------------------------------- BroadcastConstellation ---
def test_broadcast_constellation_interface_and_sky(obs, nav):
    start = obs.epochs[0].t
    con = BroadcastConstellation(nav, start, rng=np.random.default_rng(0))
    con.update_all(0.0, ideal=True)
    for s in con.satellites:
        assert s.system == "GPS" and s.enabled and s.valid
        assert np.allclose(s.current_pos, ep.sat_position(s.eph, start)[0])
        assert np.allclose(s.broadcast_pos, s.current_pos)          # ideal -> bez greške
        sig = s.get_signal(0.0)
        assert {"id", "pos", "broadcast_pos", "sat_clock_m", "broadcast_clock_m", "l1", "l2"} <= set(sig)
        assert sig["sat_clock_m"] == sig["broadcast_clock_m"]
        assert 2.6e7 < s.a < 2.66e7 and 50 < s.i < 60                # elementi za serialize
    # PRAVI sateliti iznad horizonta == oni koje je prijemnik stvarno pratio
    P = obs.header.approx_pos
    above = {s.sat_id for s in con.satellites if realdata.az_el(P, s.current_pos)[1] > np.radians(5)}
    tracked = set(obs.epochs[0].obs)
    assert tracked <= above and len(above - tracked) <= 2
    # nakon 1 h: pozicija i dalje iz (eventualno nove) važeće efemeride
    con.update_all(3600.0, ideal=True)
    for s in con.satellites:
        assert np.allclose(s.current_pos, ep.sat_position(s.eph, start + 3600.0)[0])


def test_broadcast_constellation_with_receiver(obs, nav):
    start = obs.epochs[0].t
    P = obs.header.approx_pos.copy()
    # ideal: zero-noise konzistencija (isti test kao za Walker-Delta, test_consistency)
    rng = np.random.default_rng(3)
    con = BroadcastConstellation(nav, start, rng=rng)
    rx = Receiver(P.copy(), rng=rng, ideal=True)
    rx.iono_tow0 = con.start_tow % 86400.0
    errs = []
    for t in range(20):
        con.update_all(float(t), ideal=True)
        rx.receive_signals(con, float(t))
        pos, _ = rx.solve_position()
        errs.append(np.linalg.norm(pos - P))
    # (kao test_consistency: cm razina; prvi koraci EKF-a malo zaostaju)
    assert errs[-1] < 0.01 and max(errs) < 0.05 and len(rx.received_signals) >= 6
    # s šumom (RF kanal, efemeridna greška, satovi): realistična greška
    rng = np.random.default_rng(4)
    con = BroadcastConstellation(nav, start, rng=rng)
    rx = Receiver(P.copy(), rng=rng)
    errs = []
    for t in range(20):
        con.update_all(float(t))
        rx.receive_signals(con, float(t))
        pos, _ = rx.solve_position()
        if pos is not None:
            errs.append(np.linalg.norm(pos - P))
    assert len(errs) >= 18 and np.median(errs) < 20.0


def test_broadcast_constellation_user_faults(obs, nav):
    con = BroadcastConstellation(nav, obs.epochs[0].t, rng=np.random.default_rng(0))
    s = con.satellites[0]
    s.user_clock_offset_m = 50.0
    s.user_pos_offset_m = 100.0
    con.update_all(0.0, ideal=True)
    sig = s.get_signal(0.0)
    assert sig["sat_clock_m"] - sig["broadcast_clock_m"] == pytest.approx(50.0)
    assert np.linalg.norm(sig["broadcast_pos"]) - np.linalg.norm(sig["pos"]) == pytest.approx(100.0, abs=1e-6)


# ---------------------------------------------------------------- web API ---
def test_realdata_endpoint():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from web.backend.app import app
    r = TestClient(app).post("/api/realdata", json={"mask_deg": 10}).json()
    assert r["ok"] and r["solved"] == r["n_epochs"] == 120
    assert len(r["t"]) == len(r["h_err"]) == len(r["v_err"]) == len(r["nsat"]) == 120
    assert r["summary"]["h_median"] < 1.5 and r["station"] == "0759"
    assert "RTKLIB" in r["source"]
