"""REST eksperimenti — tanki wrapperi oko postojećih analiza (vraćaju JSON).

Svaki endpoint parsira JSON body i zove postojeću funkciju enginea; rezultat se
provuče kroz `to_jsonable`. Grafove crta frontend iz ovih podataka (matplotlib
nije potreban).
"""
from fastapi import APIRouter, Body

import rtk
import iono
import multignss
import skyplot
import benchmark
from spoofing import run_attack
from scenario import build_attack
from web.backend.serialize import to_jsonable

router = APIRouter()


@router.post("/rtk")
def api_rtk(p: dict = Body(...)):
    rover = p.get("rover", {})
    base = p.get("base", {})
    res = rtk.rtk_solve(
        (rover.get("lat", 45.815), rover.get("lon", 15.982), rover.get("alt", 120.0)),
        (base.get("lat", 45.815), base.get("lon", 16.046), base.get("alt", 120.0)),
        n_epochs=int(p.get("n_epochs", 40)), dt_epoch=float(p.get("dt_epoch", 30.0)),
        seed=int(p.get("seed", 0)), mask_deg=float(p.get("mask_deg", 15.0)),
    )
    if res is None:
        return {"ok": False, "reason": "Premalo zajedničkih satelita kroz sve epohe."}
    return {"ok": True, **to_jsonable(res)}


@router.post("/spoofing")
def api_spoofing(p: dict = Body(...)):
    spec = p.get("attack")
    if isinstance(spec, str):          # frontend šalje samo naziv -> koristi zadane parametre
        spec = {"type": spec}
    attack = build_attack(spec)
    data = run_attack(
        float(p.get("lat", 45.815)), float(p.get("lon", 15.982)), float(p.get("alt", 120.0)),
        attack, seconds=int(p.get("seconds", 300)), seed=int(p.get("seed", 1234)),
    )
    data.pop("target", None)   # ECEF cilj nije potreban frontendu
    return to_jsonable(data)


@router.post("/multignss")
def api_multignss(p: dict = Body(...)):
    data = multignss.run_compare(
        float(p.get("lat", 45.815)), float(p.get("lon", 15.982)), float(p.get("alt", 120.0)),
        mask_deg=float(p.get("mask_deg", 10.0)), seed=int(p.get("seed", 1234)),
    )
    return to_jsonable(data)


@router.post("/iono")
def api_iono(p: dict = Body(...)):
    return to_jsonable(iono.run(float(p.get("lat", 45.815)), float(p.get("lon", 15.982))))


@router.post("/skyplot")
def api_skyplot(p: dict = Body(...)):
    return to_jsonable(skyplot.run(
        float(p.get("lat", 45.815)), float(p.get("lon", 15.982)), float(p.get("alt", 120.0)),
        int(p.get("seconds", 300)), int(p.get("seed", 1234)),
    ))


@router.post("/benchmark")
def api_benchmark(p: dict = Body(...)):
    errors, gdops, alarms, nis = benchmark.run_scenario(
        float(p.get("lat", 45.815)), float(p.get("lon", 15.982)), float(p.get("alt", 120.0)),
        int(p.get("seconds", 300)), seed=int(p.get("seed", 1234)),
    )
    import numpy as np
    conv = errors[len(errors) // 2:] if len(errors) else errors
    return to_jsonable({
        "errors": errors, "gdops": gdops, "nis": nis, "alarms": alarms,
        "summary": {
            "solved": len(errors),
            "median_err": float(np.median(errors)) if len(errors) else None,
            "conv_mean": float(conv.mean()) if len(conv) else None,
            "conv_p95": float(np.percentile(conv, 95)) if len(conv) else None,
            "max_err": float(errors.max()) if len(errors) else None,
            "gdop_mean": float(gdops.mean()) if len(gdops) else None,
            "nis_mean": float(nis.mean()) if len(nis) else None,
            "raim_alarms": len(alarms),
        },
    })
