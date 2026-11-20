"""Pogled iznutra (/api/inspect): međuveličine epohe su potpune i međusobno dosljedne."""
import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from web.backend.sim_session import SimSession  # noqa: E402
from web.backend.inspect_epoch import build_inspect  # noqa: E402


@pytest.fixture(scope="module")
def snap():
    s = SimSession(seed=7)
    s.set_receiver(45.815, 15.982, 120.0)
    for _ in range(20):
        s.advance(5.0)
    return s, build_inspect(s)


def test_unavailable_before_receiver():
    assert build_inspect(SimSession(seed=1))["available"] is False


def test_model_and_innovation_are_consistent(snap):
    _, d = snap
    assert d["available"]
    for m in d["measurements"]:
        mod = m["model"]
        pred = mod["geometric"] + mod["clock"] + mod["sagnac"] + mod["isb"]
        assert pred == pytest.approx(mod["predicted"], abs=0.01)
        assert m["pseudorange"] - mod["predicted"] == pytest.approx(m["innovation"], abs=0.01)
        # proračun greške se zbraja u ukupnu grešku mjerenja
        assert sum(m["error_budget"].values()) == pytest.approx(m["error_total"], abs=0.01)
        # bez napada je ostatak (multipath + šum) malen
        assert abs(m["error_budget"]["remainder"]) < 60.0


def test_geometry_dops_match_receiver(snap):
    s, d = snap
    g = d["geometry"]
    assert g["n"] == len(g["rows"]) >= 4
    dop = g["dop"]
    assert dop["HDOP"] ** 2 == pytest.approx(dop["EDOP"] ** 2 + dop["NDOP"] ** 2, rel=1e-2)
    assert dop["GDOP"] == pytest.approx(s.gdop, rel=0.05)      # isti GDOP kao prijemnik


def test_kalman_correction_and_contributions(snap):
    _, d = snap
    k = d["kalman"]
    corr = np.array(k["correction_enu"])
    assert np.allclose(np.array(k["updated"]["enu"]) - np.array(k["predicted"]["enu"]), corr, atol=0.01)
    contrib = np.sum([m["contribution_enu"] for m in d["measurements"] if m.get("contribution_enu")], axis=0)
    assert np.allclose(contrib, corr, atol=0.05)                # korekcija = Σ K_j·y_j
    assert all(u <= p + 1e-6 for u, p in zip(k["updated"]["std_enu"], k["predicted"]["std_enu"]))


def test_raim_view_matches_integrity(snap):
    s, d = snap
    r = d["raim"]
    assert r["test"] == pytest.approx(s.receiver.integrity["test"], rel=1e-3)
    hpl = max(x["hslope"] for x in r["sats"]) * r["pbias"]
    assert hpl == pytest.approx(s.receiver.integrity["hpl"], rel=1e-2)
    assert len(r["pdf_x"]) == len(r["pdf_y"]) > 50
