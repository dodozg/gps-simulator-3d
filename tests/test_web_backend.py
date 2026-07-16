"""Web backend (#12): serijalizacija, REST eksperimenti i WebSocket živa sim.

Preskače se ako web ovisnosti (fastapi/httpx) nisu instalirane — CI (numpy+pytest)
ostaje zelen bez njih. Lokalno: pip install -r requirements-web.txt + httpx.
"""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from web.backend.app import app  # noqa: E402
from web.backend.sim_session import SimSession  # noqa: E402
from web.backend.serialize import state_frame, to_jsonable  # noqa: E402

client = TestClient(app)


def test_health_and_constellation():
    assert client.get("/api/health").json()["status"] == "ok"
    con = client.get("/api/constellation").json()
    assert con["gps"]["n_sats"] == 24 and len(con["gps"]["planes"]) == 6
    assert set(con["systems"]) == {"GPS", "GAL", "GLO", "BDS"}


def test_to_jsonable_handles_nan_and_numpy():
    import numpy as np
    out = to_jsonable({"a": np.array([1.0, np.nan, np.inf]), "b": np.int64(3)})
    assert out["a"] == [1.0, None, None] and out["b"] == 3


def test_experiment_endpoints():
    r = client.post("/api/rtk", json={"rover": {"lat": 45.815, "lon": 15.982, "alt": 120},
                                      "base": {"lat": 45.815, "lon": 16.05, "alt": 120}}).json()
    assert r["ok"] and r["fixed_err_m"] < 0.1
    r = client.post("/api/multignss", json={"lat": 45.815, "lon": 15.982, "mask_deg": 10}).json()
    assert r["all"][0] > r["gps"][0]                       # više satelita s više sustava
    r = client.post("/api/iono", json={"lat": 45.815, "lon": 15.982}).json()
    assert 13 <= r["peak"][0] <= 15                         # vrh oko 14 h


def test_spoofing_endpoint_accepts_attack_string():
    # frontend šalje samo naziv napada -> backend ga umota u {"type": ...}
    r = client.post("/api/spoofing", json={"lat": 45.815, "lon": 15.982,
                                           "seconds": 90, "attack": "coordinated"}).json()
    assert r["attack_name"] == "coordinated"
    assert len(r["errors"]) == 90 and isinstance(r["fix_lost"], list)
    assert r["window"] == [60.0, 240.0]                     # zadani parametri napada


def test_lessons_have_driving_steps():
    # Vođene lekcije moraju imati korake s valjanim akcijama koje pogone panel.
    valid = {"place", "attack", "time_of_day", "raim", "kinematic",
             "speed", "play", "pause", "reset", "experiment"}
    for lang in ("hr", "en"):
        data = client.get(f"/api/lessons?lang={lang}").json()["lessons"]
        assert len(data) == 6
        assert sum(len(l["steps"]) for l in data) >= 20
        for les in data:
            assert les["steps"], f"{les['id']} bez koraka"
            for s in les["steps"]:
                assert s["text"]
                if "action" in s:
                    assert s["action"]["do"] in valid


def test_scenario_list_and_compare():
    files = [s["file"] for s in client.get("/api/scenario/list").json()["scenarios"]]
    assert "zagreb_clean.json" in files
    r = client.post("/api/scenario/compare", json={"file": "jamming_naive_spoof.json"}).json()
    assert r["mode"] == "raim"
    assert r["a"]["result"]["median_err"] < r["b"]["result"]["median_err"] / 5


def test_live_attack_window_anchors_to_now():
    # Živa sesija ima veliki sim_time; zadani prozor napada (60-240 s apsolutno)
    # ne bi se nikad aktivirao -> set_attack sidri prozor relativno na sada.
    s = SimSession(seed=1)
    s.set_receiver(45.815, 15.982, 120.0)
    for _ in range(50):
        s.advance(5.0)                                     # sim_time = 250 s
    s.set_attack("jamming")                                # prima i goli string
    assert s.attack["start"] >= 250.0 and not s.attack_active()
    s.advance(5.0)                                         # uđi u prozor
    assert s.attack_active()
    f = state_frame(s)
    assert f["attack_active"] is True and f["attack"]["type"] == "jamming"
    s.set_attack(None)
    assert state_frame(s)["attack_active"] is False


def test_diverged_estimate_ecef_serializes_null():
    # Kolabirana/nekonačna EKF procjena ne smije proći kao sirovi broj: frontend
    # (Cesium) ne može projicirati takvu točku i sruši render loop. -> None.
    import numpy as np
    s = SimSession(seed=1234)
    s.set_receiver(45.815, 15.982, 120.0)
    for _ in range(10):
        s.advance(1.0)
    s.calc_pos = np.array([np.nan, np.nan, np.nan])   # simuliraj divergenciju
    f = state_frame(s)
    assert f["receiver"]["estimate"]["ecef"] == [None, None, None]
    assert f["receiver"]["estimate"]["dms"]["lat"] is None


def test_state_frame_shape():
    s = SimSession(seed=1234)
    s.set_receiver(45.815, 15.982, 120.0)
    for _ in range(30):
        s.advance(1.0)
    f = state_frame(s)
    # Živa sesija sad vrti sve GNSS konstelacije (96 sat.), ali je po defaultu
    # aktivan samo GPS (24) -> u rješenje ulaze samo upaljeni.
    assert f["sats_total"] == 96 and f["receiver"]["placed"]
    assert len(f["satellites"]) == 96
    assert f["systems"]["GPS"]["on"] is True and f["systems"]["GAL"]["on"] is False
    assert f["systems"]["GPS"]["enabled"] == 24
    assert sum(1 for x in f["satellites"] if x["enabled"]) == 24    # samo GPS upaljen
    assert f["receiver"]["ekf_initialized"]


def test_websocket_live_sim_converges():
    with client.websocket_connect("/ws/sim") as ws:
        ws.receive_json()                                   # početni frame
        ws.send_json({"type": "set_receiver", "lat": 45.815, "lon": 15.982, "alt": 120})
        ws.send_json({"type": "time_scale", "value": 200})
        ws.send_json({"type": "play"})
        f = None
        for _ in range(12):
            f = ws.receive_json()
        assert f["receiver"]["placed"] and f["receiver"]["ekf_initialized"]
        assert f["sats_tracked"] >= 4
