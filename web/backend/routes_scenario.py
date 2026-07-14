"""REST scenariji — list / run / compare / save (reuse scenario.py)."""
import glob
import os

from fastapi import APIRouter, Body, HTTPException

from scenario import Scenario, run_scenario, SCENARIO_DIR
from web.backend.serialize import to_jsonable

router = APIRouter()


def _scn_from_body(p):
    """Napravi Scenario iz body-ja: ili {"file": naziv} ili {"scenario": {...}}."""
    if p.get("file"):
        path = os.path.join(SCENARIO_DIR, os.path.basename(p["file"]))
        if not os.path.isfile(path):
            raise HTTPException(404, f"Scenarij ne postoji: {p['file']}")
        return Scenario.load(path)
    if p.get("scenario"):
        return Scenario(**p["scenario"])
    raise HTTPException(400, "Treba 'file' ili 'scenario'.")


@router.get("/list")
def api_list():
    out = []
    for f in sorted(glob.glob(os.path.join(SCENARIO_DIR, "*.json"))):
        s = Scenario.load(f)
        out.append({"file": os.path.basename(f), "name": s.name,
                    "description": s.description, "lat": s.lat, "lon": s.lon,
                    "seconds": s.seconds, "attack": s.attack["type"] if s.attack else None})
    return {"scenarios": out}


@router.post("/run")
def api_run(p: dict = Body(...)):
    scn = _scn_from_body(p)
    return {"scenario": scn.name, "raim": not p.get("no_raim", False),
            "result": to_jsonable(run_scenario(scn, raim=not p.get("no_raim", False)))}


@router.post("/compare")
def api_compare(p: dict = Body(...)):
    scnA = _scn_from_body(p)
    if p.get("other") or p.get("other_scenario"):
        scnB = _scn_from_body({"file": p.get("other"), "scenario": p.get("other_scenario")})
        return {"mode": "scenarios", "a": {"name": scnA.name, "result": to_jsonable(run_scenario(scnA))},
                "b": {"name": scnB.name, "result": to_jsonable(run_scenario(scnB))}}
    return {"mode": "raim",
            "a": {"name": "RAIM on", "result": to_jsonable(run_scenario(scnA, raim=True))},
            "b": {"name": "RAIM off", "result": to_jsonable(run_scenario(scnA, raim=False))}}


@router.post("/save")
def api_save(p: dict = Body(...)):
    scn = Scenario(**p["scenario"])
    fname = os.path.basename(p.get("filename", f"{scn.name}.json"))
    if not fname.endswith(".json"):
        fname += ".json"
    path = os.path.join(SCENARIO_DIR, fname)
    scn.save(path)
    return {"ok": True, "file": fname}
