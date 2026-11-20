"""Istraživački sandbox (sandbox.py): spec, determinizam, plugini, WLS, metrike, REST.

Runovi su namjerno kratki (desetak-dvadesetak epoha, bez terena) da cijela datoteka
traje < ~1 min; jedini višeprocesni test (workers=2) pokreće i plugin iz datoteke
kako bi se provjerilo da spawnani workeri vide iste registre.
"""
import json
import math
import os
import time

import numpy as np
import pytest

import raim
import receiver
import measurement
import sandbox
from satellite import MultiGNSSConstellation
from utils import lla_to_ecef

FAST_WORLD = {"duration_s": 20, "terrain": False}


def _spec(**kw):
    d = {"name": "t", "world": dict(FAST_WORLD), "seeds": 2, "warmup_s": 5,
         "metrics": ["availability", "h_err_median", "err3d_p95", "raim_detections",
                     "false_alarms", "hpl_median", "runtime_ms"]}
    d.update(kw)
    return d


# --------------------------------------------------------------------------- spec
def test_validate_accepts_good_spec_and_examples():
    spec, errs = sandbox.validate(_spec(sweep={"attack.bias_m": [0, 20], "raim.pfa": [1e-3, 1e-5]},
                                        attack={"type": "sat_fault", "start": 5}))
    assert errs == [] and spec is not None
    sz = sandbox.plan_size(spec)
    assert sz["points"] == 4 and sz["runs"] == 8 and sz["epochs"] == 8 * 20
    examples = sandbox.list_examples()
    assert len(examples) >= 5
    for fn, d in examples:
        s, e = sandbox.validate(d)
        assert e == [], f"{fn}: {e}"


@pytest.mark.parametrize("bad, needle", [
    ({"bogus": 1}, "nepoznat ključ speca"),
    ({"world": {"mask_deg": 2}}, "mask_deg"),
    ({"world": {"systems": ["GPS", "XYZ"]}}, "systems"),
    ({"estimators": ["nope"]}, "nije registriran"),
    ({"metrics": ["nope"]}, "nije registrirana"),
    ({"sweep": {"foo.bar": [1]}}, "nepoznat parametar"),
    ({"sweep": {"mask_deg": [10, 90]}}, "mask_deg"),           # greška tek u jednoj točki sweepa
    ({"sweep": {"raim.pfa": [0.7]}}, "raim.pfa"),
    ({"attack": {"type": "nope"}}, "attack.type"),
    ({"attack": {"type": "sat_fault", "wrong_param": 1}}, "neispravni parametri"),
    ({"sweep_mode": "zip", "sweep": {"mask_deg": [10, 20], "max_sats": [8]}}, "zip"),
    ({"seeds": [1, 1]}, "ponavljaju"),
])
def test_validate_rejects(bad, needle):
    spec, errs = sandbox.validate(_spec(**bad))
    assert spec is None
    assert any(needle in e for e in errs), errs


def test_sweep_resolution_and_zip():
    spec = sandbox.parse_spec(_spec(sweep={"mask_deg": [10, 20], "world.kinematic.speed_mps": [5, 9]},
                                    sweep_mode="zip"))
    pts = sandbox._sweep_points(spec)
    assert pts == [{"mask_deg": 10, "world.kinematic.speed_mps": 5},
                   {"mask_deg": 20, "world.kinematic.speed_mps": 9}]
    world, rcfg, attack, ests = sandbox.resolve_config(spec, pts[1], sandbox._locations(spec.world)[0])
    assert world["mask_deg"] == 20 and world["kinematic"] == {"speed_mps": 9}
    assert attack is None and ests == ["ekf"] and rcfg["pfa"] == raim.RAIM_PFA
    _, _, _, ests = sandbox.resolve_config(spec, {"estimator": "wls"}, sandbox._locations(spec.world)[0])
    assert ests == ["wls"]


# --------------------------------------------------------------------- ekvivalencija
def test_ekf_matches_scenario_runner():
    """Sandbox s EKF-om, bez maske/filtra, mora dati BAŠ isti trag kao scenario.run_scenario."""
    import scenario
    atk = {"type": "naive", "n": 2, "bias_m": 5000, "start": 10, "end": 20}
    ref = scenario.run_scenario(scenario.Scenario(seconds=25, seed=77, attack=atk))
    tr = sandbox.simulate({"world": {"duration_s": 25}, "attack": atk},
                          {}, sandbox._locations({})[0], 77)["ekf"]
    # isti algoritam; zadnja decimala smije se razlikovati (drugi BLAS / redoslijed zbrajanja)
    assert np.nanmedian(tr["err_3d"]) == pytest.approx(ref["median_err"], rel=1e-9)
    assert int(tr["detect"].sum()) == ref["raim_alarms"]


# ----------------------------------------------------------------------- RAIM postavke
def test_engine_settings_apply_and_restore():
    saved = (raim.RAIM_PFA, raim.RAIM_HAL, receiver.RAIM_SIGMA_SCALE, measurement.MAX_SATS, raim.run_raim)
    cfg = {"pfa": 1e-2, "pmd": 1e-2, "hal": 40.0, "val": 50.0, "sigma_scale": 2.0}
    G = np.hstack([np.random.default_rng(0).normal(size=(8, 3)), np.ones((8, 1))])
    y = np.random.default_rng(1).normal(size=8)
    with sandbox.engine_settings(cfg, 7):
        assert raim.RAIM_PFA == 1e-2 and receiver.RAIM_SIGMA_SCALE == 2.0 and measurement.MAX_SATS == 7
        r = raim.run_raim(G, y, np.ones(8), np.array([6.4e6, 0, 0]))   # kao što zove receiver.py
        assert r["hal"] == 40.0 and r["val"] == 50.0
        assert math.isclose(r["threshold"], raim.chi2_isf(1e-2, 4))
    assert (raim.RAIM_PFA, raim.RAIM_HAL, receiver.RAIM_SIGMA_SCALE, measurement.MAX_SATS,
            raim.run_raim) == saved


# ---------------------------------------------------------------------------- WLS
@pytest.mark.parametrize("systems", [("GPS",), ("GPS", "GAL", "GLO", "BDS")])
def test_wls_unbiased_zero_noise(systems):
    """Zero-noise (ideal) mod: WLS mora pasti na ~µm (Sagnac + sat/ISB po sustavu točno modelirani)."""
    rng = np.random.default_rng(5)
    con = MultiGNSSConstellation(systems=systems, rng=rng)
    gt = np.array(lla_to_ecef(45.815, 15.982, 120.0))
    meas = sandbox._SandboxMeasurement(gt, rng=rng, ideal=True, terrain=False)
    world = sandbox.SimpleNamespace(raim=dict(sandbox._raim_defaults()), gt0=gt, ideal=True)
    est = sandbox.WLSEstimator(world)
    errs = []
    for t in range(12):
        con.update_all(float(t), ideal=True)
        e = est.estimate()
        sig = meas.build(con, float(t), est_pos=e, ref_pos=e if e is not None else gt)
        pos, info = est.solve(sig, float(t))
        assert pos is not None and info["status"] in ("ok", "excluded")
        assert not info["excluded"]                         # bez šuma nema lažnog isključenja
        errs.append(np.linalg.norm(pos - gt))
    assert max(errs[1:]) < 0.01, errs


def test_wls_raim_excludes_faulty_satellite():
    spec = _spec(estimators=["wls"], attack={"type": "sat_fault", "bias_m": 300, "start": 5},
                 metrics=["raim_pd", "correct_exclusion_rate", "h_err_p95"])
    traces = sandbox.simulate(spec, {}, sandbox._locations({})[0], 3)
    m = sandbox.compute_metrics(traces["wls"], spec["metrics"])
    assert m["raim_pd"] == 1.0 and m["correct_exclusion_rate"] == 1.0
    assert m["h_err_p95"] < 30


# ------------------------------------------------------------------------ metrike
def _synthetic_trace():
    n = 10
    t = np.arange(n, dtype=float)
    fix = np.array([1, 1, 1, 0, 0, 1, 1, 1, 0, 1], bool)
    err_h = np.where(fix, [1, 2, 3, 0, 0, 10, 2, 30, 0, 4], np.nan).astype(float)
    hpl = np.where(fix, [5, 5, 5, 0, 0, 5, 5, 50, 0, 600], np.nan).astype(float)
    detect = np.array([0, 1, 0, 0, 0, 0, 1, 1, 0, 0], bool)
    active = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], bool)
    tr = {"t": t, "fix": fix, "err_h": err_h, "err_v": err_h / 2, "err_3d": err_h * 1.5,
          "hpl": hpl, "vpl": hpl, "detect": detect, "excluded_n": detect.astype(float),
          "faulty_excluded": detect & active, "fault_present": active.copy(), "attack_active": active,
          "n_sats": np.full(n, 8.0), "nis_norm": np.where(fix, 1.0, np.nan),
          "gdop": np.where(fix, 2.0, np.nan), "runtime_s": np.full(n, 0.002),
          "target_dist": np.full(n, np.nan),
          "meta": {"hal": 556.0, "val": None, "warmup_s": 1.0, "has_attack": True,
                   "attack_start": 5.0, "has_faulty": True}}
    return tr


def test_builtin_metrics_on_synthetic_trace():
    tr = _synthetic_trace()
    m = sandbox.compute_metrics(tr, list(sandbox.METRICS))
    assert "_errors" not in m
    assert m["availability"] == 0.7
    # točnost: fix i t ≥ 1 -> err_h = [2, 3, 10, 2, 30, 4]
    assert m["h_err_median"] == 3.5 and m["h_err_max"] == 30 and m["h_err_mean"] == 51 / 6
    assert math.isclose(m["err3d_median"], 5.25)
    assert m["integrity_availability"] == 0.6           # 6 fixeva s HPL ≤ 556 (t=9 ima 600)
    assert m["raim_detections"] == 2 and m["raim_pd"] == 0.4
    assert m["false_alarms"] == 1                        # t=1 (t=0 je unutar warmupa)
    assert m["time_to_detect"] == 1.0                    # prva detekcija za napada u t=6
    assert m["correct_exclusion_rate"] == 0.4
    # MI: err_h > HPL i bez alarma: t=5 (10 > 5); t=7 ima alarm, t=9 ne (4 < 600)
    assert m["mi_events"] == 1 and math.isclose(m["mi_rate"], 1 / 6)
    assert m["hmi_events"] == 0
    assert m["fix_loss_count"] == 2 and m["no_fix_epochs"] == 3
    assert m["hpl_max"] == 600 and m["nis_mean"] == 1.0
    assert math.isclose(m["runtime_ms"], 2.0)
    assert m["final_err"] == 1.5 * 3.0                 # medijan svih 7 fixeva


def test_summarize_ci():
    s = sandbox.summarize([1.0, 2.0, 3.0, 4.0, float("nan"), None])
    assert s["n"] == 4 and s["mean"] == 2.5 and s["median"] == 2.5
    half = 3.182 * np.std([1, 2, 3, 4], ddof=1) / 2
    assert math.isclose(s["ci_hi"] - s["mean"], half) and math.isclose(s["mean"] - s["ci_lo"], half)
    assert math.isnan(sandbox.summarize([5.0])["ci_lo"])
    assert sandbox.t_crit_975(1000) < sandbox.t_crit_975(100) < sandbox.t_crit_975(35) < 2.04


# ------------------------------------------------------------------ plugini + determinizam
PLUGIN_SRC = '''
import numpy as np
import sandbox

@sandbox.register_metric("test_err_sum")
def err_sum(tr):
    """zbroj horizontalnih grešaka (test plugin)"""
    return float(np.nansum(tr["err_h"]))
'''


@sandbox.register_estimator("test_hold_first")
class HoldFirst:
    """Testni estimator: prvo WLS rješenje pa ga drži (statičan prijemnik)."""

    def __init__(self, world):
        self.inner = sandbox.WLSEstimator(world)
        self.pos = None

    def solve(self, signals, t):
        if self.pos is None:
            self.pos, _ = self.inner.solve(signals, t)
        return self.pos, {"status": "ok"}


@sandbox.register_attack("test_drop_all_after")
class DropAll:
    """Testni napad: od t0 nadalje izbaci sva mjerenja."""

    def __init__(self, t0=10.0):
        self.start = float(t0)

    def is_active(self, t):
        return t >= self.start

    def apply(self, signals, t, rx_pos, rng):
        if self.is_active(t):
            signals[:] = []


def test_inline_plugins_registered_and_used():
    assert "test_hold_first" in sandbox.ESTIMATORS and "test_drop_all_after" in sandbox.ATTACKS
    res = sandbox.run(_spec(estimators=["test_hold_first", "wls"], seeds=1,
                            attack={"type": "test_drop_all_after", "t0": 10},
                            metrics=["availability", "no_fix_epochs", "h_err_max"]))
    rows = {a["estimator"]: a["metrics"] for a in res.aggregate}
    assert rows["wls"]["availability"]["mean"] == 0.5          # 10 od 20 epoha
    assert rows["test_hold_first"]["availability"]["mean"] == 1.0   # drži zadnje rješenje
    assert rows["wls"]["no_fix_epochs"]["mean"] == 10


def test_determinism_workers_and_file_plugin(tmp_path):
    plug = tmp_path / "myplug.py"
    plug.write_text(PLUGIN_SRC, encoding="utf-8")
    spec = _spec(sweep={"attack.bias_m": [0.0, 40.0]}, seeds=2, estimators=["ekf", "wls"],
                 attack={"type": "sat_fault", "start": 8}, plugins=[str(plug)],
                 metrics=["h_err_median", "raim_pd", "test_err_sum", "runtime_ms"])
    r1 = sandbox.run(spec, workers=1)
    r1b = sandbox.run(spec, workers=1)
    r2 = sandbox.run(spec, workers=2)
    assert r1.meta["runs_done"] == 4 and r2.meta["runs_done"] == 4
    assert r1.deterministic_view() == r1b.deterministic_view()
    assert r1.deterministic_view() == r2.deterministic_view()
    assert "runtime_ms" in r1.meta["nondeterministic_metrics"]
    assert "runtime_ms" not in r1.deterministic_view()[0]["metrics"]
    # metrika iz plugina je stvarno izračunata (i u worker procesima)
    assert all(a["metrics"]["test_err_sum"]["n"] == 2 for a in r2.aggregate)
    # različita sjemena -> različiti rezultati (Monte Carlo nije degeneriran)
    runs = [r for r in r1.runs if r["estimator"] == "ekf" and r["point"] == 0]
    assert runs[0]["metrics"]["h_err_median"] != runs[1]["metrics"]["h_err_median"]


def test_result_export_and_plot(tmp_path):
    res = sandbox.run(_spec(sweep={"raim.enabled": [True, False]}, seeds=2, save_traces=True,
                            world=dict(FAST_WORLD, duration_s=12)))
    paths = res.save(str(tmp_path))
    d = json.loads(open(paths["json"], encoding="utf-8").read())
    assert d["spec"]["sweep"] == {"raim.enabled": [True, False]}
    assert len(d["aggregate"]) == 2 and len(d["runs"]) == 4
    assert "git" in d["meta"]
    lines = open(paths["aggregate"], encoding="utf-8").read().strip().splitlines()
    assert lines[0].startswith("point,raim.enabled,estimator,availability_mean")
    assert len(lines) == 3
    assert len(os.listdir(paths["traces"])) == 4
    # RAIM isključen -> nema HPL-a
    off = [a for a in res.aggregate if a["params"]["raim.enabled"] is False][0]
    assert off["metrics"]["hpl_median"]["n"] == 0
    pytest.importorskip("matplotlib")
    png = res.plot(metric="h_err_median", out=str(tmp_path / "p.png"))
    assert os.path.getsize(png) > 1000


def test_cancel_returns_partial_result():
    class Ev:
        def __init__(self):
            self.n = 0

        def is_set(self):
            self.n += 1
            return self.n > 1        # dopusti samo prvi run
    res = sandbox.run(_spec(seeds=3, world=dict(FAST_WORLD, duration_s=5)), cancel=Ev())
    assert res.meta["cancelled"] and res.meta["runs_done"] == 1
    assert res.aggregate[0]["metrics"]["availability"]["n"] == 1


def test_cli_validate_and_list(capsys):
    ex = os.path.join(sandbox.EXAMPLES_DIR, sandbox.list_examples()[0][0])
    assert sandbox.main(["validate", ex]) == 0
    assert "OK" in capsys.readouterr().out
    assert sandbox.main(["list"]) == 0
    out = capsys.readouterr().out
    for name in ("ekf", "wls", "sat_fault", "coordinated", "mi_events", "time_to_detect"):
        assert name in out


# ---------------------------------------------------------------------------- REST
def test_rest_job_flow():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from web.backend.app import app
    client = TestClient(app)

    ex = client.get("/api/sandbox/examples").json()
    assert len(ex["examples"]) >= 5 and ex["limits"]["max_runs"] > 0

    bad = client.post("/api/sandbox/validate", json={"spec": {"world": {"mask_deg": 1}}}).json()
    assert not bad["ok"] and bad["errors"]
    big = client.post("/api/sandbox/run", json={"spec": _spec(seeds=500)})
    assert big.status_code == 400 and "previše" in json.dumps(big.json(), ensure_ascii=False)
    assert client.post("/api/sandbox/run", json={"spec": _spec(plugins=["x"])}).status_code == 400
    pv = client.post("/api/sandbox/validate", json={"spec": _spec(plugins=["os"])}).json()
    assert not pv["ok"] and "plugins" in pv["errors"][0]

    spec = _spec(sweep={"mask_deg": [5, 15]}, seeds=1, world=dict(FAST_WORLD, duration_s=8))
    ok = client.post("/api/sandbox/validate", json={"spec": spec}).json()
    assert ok["ok"] and ok["size"]["runs"] == 2
    r = client.post("/api/sandbox/run", json={"spec": spec, "workers": 1})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    t0 = time.time()
    while True:
        st = client.get(f"/api/sandbox/jobs/{jid}").json()
        if st["status"] not in ("queued", "running"):
            break
        assert time.time() - t0 < 60
        time.sleep(0.2)
    assert st["status"] == "done", st
    assert st["done"] == st["total"] == 2
    agg = st["result"]["aggregate"]
    assert [a["params"]["mask_deg"] for a in agg] == [5, 15]
    csv_r = client.get(f"/api/sandbox/jobs/{jid}/csv")
    assert csv_r.status_code == 200 and csv_r.text.startswith("point,mask_deg,estimator")
    assert "attachment" in csv_r.headers["content-disposition"]
    assert client.get("/api/sandbox/jobs/nope").status_code == 404


def test_t0_random_varies_geometry_not_noise_stream():
    """t0_random_s: svako sjeme dobije drugu geometriju (Monte Carlo geometrije)."""
    base = {"world": {"duration_s": 3, "terrain": False}}
    loc = sandbox._locations({})[0]
    g = [sandbox.simulate(base, {}, loc, s)["ekf"]["gdop"][-1] for s in (1, 2)]
    assert abs(g[0] - g[1]) < 1e-3                        # ista geometrija bez t0_random_s
    rnd = {"world": {"duration_s": 3, "terrain": False, "t0_random_s": 86164}}
    tr = [sandbox.simulate(rnd, {}, loc, s)["ekf"] for s in (1, 2)]
    assert tr[0]["meta"]["t0"] != tr[1]["meta"]["t0"] and 0 < tr[0]["meta"]["t0"] < 86164
    assert abs(tr[0]["gdop"][-1] - tr[1]["gdop"][-1]) > 1e-2
    assert tr[0]["fix"].all() and tr[1]["fix"].all()


def test_terrain_false_disables_los_even_below_dem():
    # Quito u DEM-u leži na ~4300 m; prijemnik na 2850 m bi bez isključenog
    # terena bio "pod zemljom". terrain: false mora isključiti LOS provjeru.
    import sandbox
    res = sandbox.run({"world": {"duration_s": 40, "systems": ["GPS"], "terrain": False,
                                 "locations": [{"name": "Quito", "lat": -0.18, "lon": -78.47, "alt": 2850}]},
                       "seeds": 1, "estimators": ["ekf"], "metrics": ["availability"], "warmup_s": 10},
                      workers=1)
    assert float(res.table("availability")[0]) > 0.9
