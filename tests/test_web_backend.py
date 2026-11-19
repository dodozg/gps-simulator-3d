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


def test_guide_serves_markdown_in_both_languages():
    # Vodič mora postojati kao Markdown sa ~20 sekcija (## naslovi) na oba jezika.
    hr = client.get("/api/guide?lang=hr").json()
    assert hr["lang"] == "hr"
    assert "# GPS Simulator 3D" in hr["md"]
    assert hr["md"].count("\n## ") >= 15
    en = client.get("/api/guide?lang=en").json()
    assert en["lang"] == "en"
    assert "explained like you're 13" in en["md"]
    assert en["md"].count("\n## ") >= 15
    assert en["md"] != hr["md"]                   # stvarni prijevod, ne fallback
    # Nepoznat jezik pada natrag na hrvatski (ne 404).
    other = client.get("/api/guide?lang=de").json()
    assert other["lang"] == "hr"


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


def test_live_attack_stays_active_and_visible_after_ramp():
    # Nakon rampe napad i dalje DJELUJE (drži punu snagu) — pa ga i prikaz mora
    # javljati kao aktivan. Prije: učinak je ostajao, a UI je javljao "nema napada".
    s = SimSession(seed=1)
    s.set_receiver(45.815, 15.982, 120.0)
    for _ in range(10):
        s.advance(5.0)
    s.set_attack("jamming")
    end = s._attack_obj.end
    while s.sim_time < end + 60:
        s.advance(30.0)
    f = state_frame(s)
    assert f["attack_active"] is True and f["attack_overlay"]["active"] is True
    assert f["sats_tracked"] == 0                       # jamming i dalje guši signale
    s.set_attack(None)                                  # korisnik ugasi napad
    s.advance(5.0)
    assert state_frame(s)["attack_active"] is False and len(s.tracked_ids) >= 4


def test_coordinated_spoof_follows_relocated_receiver():
    # Cilj spoofa je relativan na TRENUTNU poziciju: nakon premještanja rovera
    # (Zagreb -> Tokio) procjena ne smije odletjeti natrag na staru lokaciju.
    import numpy as np
    s = SimSession(seed=1)
    s.set_receiver(45.815, 15.982, 120.0)
    for _ in range(20):
        s.advance(5.0)
    s.set_attack({"type": "coordinated", "offset_e": 600.0})
    for _ in range(10):
        s.advance(5.0)
    s.set_receiver(35.68, 139.69)
    for _ in range(60):
        s.advance(5.0)
    tgt = s._attack_obj.target_ecef(s.gt_pos)
    assert abs(np.linalg.norm(tgt - s.gt_pos) - 600.0) < 1.0
    assert np.linalg.norm(s.calc_pos - s.gt_pos) < 5_000.0


def test_frame_reports_model_time_of_day_and_actual_speed():
    s = SimSession(seed=1)
    s.set_receiver(45.815, 15.982, 120.0)
    s.set_iono_tow0(50400.0)
    for _ in range(4):
        s.advance(30.0)
    f = state_frame(s)
    assert abs(f["tow_now"] - (50400.0 + 120.0)) < 1e-6
    assert f["time_scale_actual"] == 0.0                # mjeri ga tek SimRunner


def test_websocket_bad_message_keeps_connection():
    with client.websocket_connect("/ws/sim") as ws:
        ws.receive_json()
        ws.send_text("ovo nije json")
        ws.send_json({"type": "set_receiver", "lat": "abc", "lon": 1})
        ws.send_json({"type": "nepoznato"})
        ws.send_json({"type": "set_receiver", "lat": 45.815, "lon": 15.982, "alt": 120})
        f = None
        for _ in range(5):
            f = ws.receive_json()
        assert f["receiver"]["placed"]                  # veza je preživjela loše poruke


def test_two_clients_share_one_simulation_loop():
    # Dva taba ne smiju dvostruko ubrzati simulaciju: jedna petlja, svi klijenti.
    from web.backend.routes_sim import get_runner
    with client.websocket_connect("/ws/sim") as a, client.websocket_connect("/ws/sim") as b:
        a.receive_json(); b.receive_json()
        a.receive_json(); b.receive_json()
        runner = get_runner(app)
        assert len(runner.clients) == 2
        fa, fb = a.receive_json(), b.receive_json()
        assert abs(fa["sim_time"] - fb["sim_time"]) <= 30.0
