"""Scenariji (#10): round-trip JSON, determinizam reprodukcije, usporedba algoritama."""
import os

from spoofing import NoAttack, CoordinatedSpoof, Jamming
from scenario import Scenario, build_attack, run_scenario, SCENARIO_DIR


def test_save_load_roundtrip(tmp_path):
    scn = Scenario(name="t", lat=1.0, lon=2.0, alt=3.0, seconds=10, seed=7,
                   attack={"type": "jamming", "js_db": 40.0, "start": 5, "end": 8})
    p = os.path.join(tmp_path, "s.json")
    scn.save(p)
    back = Scenario.load(p)
    assert back == scn                                   # dataclass jednakost po poljima


def test_build_attack_maps_types():
    assert isinstance(build_attack(None), NoAttack)
    assert isinstance(build_attack({"type": "coordinated", "offset_e": 500}), CoordinatedSpoof)
    assert isinstance(build_attack({"type": "jamming", "js_db": 30}), Jamming)


def test_replay_is_deterministic():
    scn = Scenario(name="det", seconds=60, seed=1234, attack=None)
    a = run_scenario(scn)
    b = run_scenario(scn)
    assert a == b                                        # isti seed -> identične metrike


def test_raim_helps_against_naive_spoof():
    scn = Scenario(name="naive", seconds=200, seed=1234,
                   attack={"type": "naive", "n": 2, "bias_m": 5000.0,
                           "start": 40.0, "end": 160.0})
    on = run_scenario(scn, raim=True)
    off = run_scenario(scn, raim=False)
    assert on["raim_alarms"] > 40 and off["raim_alarms"] == 0
    assert on["median_err"] < off["median_err"] / 5     # RAIM drastično smanjuje grešku


def test_bundled_scenarios_load_and_run():
    for name in ("zagreb_clean", "tokyo_terrain"):
        scn = Scenario.load(os.path.join(SCENARIO_DIR, f"{name}.json"))
        m = run_scenario(Scenario(**{**scn.__dict__, "seconds": 60}))
        assert m["solved"] > 30                          # oba moraju dobiti fix
        assert m["median_err"] < 200.0
