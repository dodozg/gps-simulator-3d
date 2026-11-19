"""REST istraživački sandbox — pozadinski jobovi nad `sandbox.run`.

    GET  /api/sandbox/examples          primjeri iz sandbox/examples (spec + opis)
    POST /api/sandbox/validate          {spec} -> {ok, errors, size}
    POST /api/sandbox/run               {spec | example, workers?} -> {job_id}
    GET  /api/sandbox/jobs/{id}         status, napredak, rezultat (agregat) kad je gotov
    GET  /api/sandbox/jobs/{id}/csv     agregirani rezultati kao CSV (?kind=runs za po runu)
    POST /api/sandbox/jobs/{id}/cancel  prekid (između runova)

Lokalni server štitimo ograničenjima: najviše MAX_ACTIVE_JOBS jobova istovremeno,
najviše MAX_RUNS runova (točke × lokacije × sjemena) i MAX_EPOCHS epoha·estimatora
po jobu, i najviše MAX_WORKERS procesa po jobu. Job se vrti u pozadinskoj niti;
s workers > 1 posao rade zasebni procesi (spawn), pa server ostaje responzivan.
"""
import os
import threading
import time
import uuid

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import PlainTextResponse

import sandbox

router = APIRouter()

MAX_ACTIVE_JOBS = 1
MAX_RUNS = 240
MAX_EPOCHS = 40000
MAX_WORKERS = 2
MAX_KEPT_JOBS = 20

_jobs = {}
_lock = threading.Lock()


def _example_specs():
    return {fn: d for fn, d in sandbox.list_examples()}


@router.get("/examples")
def api_examples():
    out = []
    for fn, d in sandbox.list_examples():
        try:
            size = sandbox.plan_size(d)
        except Exception:  # noqa: BLE001
            size = None
        out.append({"file": fn, "name": d.get("name", fn), "description": d.get("description", ""),
                    "spec": d, "size": size})
    return {"examples": out, "limits": {"max_runs": MAX_RUNS, "max_epochs": MAX_EPOCHS,
                                        "max_workers": MAX_WORKERS}}


def _check(spec_d):
    spec, errs = sandbox.validate(spec_d)
    if errs:
        return None, errs, None
    size = sandbox.plan_size(spec)
    lim = []
    if size["runs"] > MAX_RUNS:
        lim.append(f"previše runova: {size['runs']} > {MAX_RUNS} (smanji sweep ili sjemena)")
    if size["epochs"] > MAX_EPOCHS:
        lim.append(f"previše epoha: {size['epochs']} > {MAX_EPOCHS} (smanji duration_s/sjemena)")
    return spec, lim, size


@router.post("/validate")
def api_validate(p: dict = Body(...)):
    spec_d = p.get("spec")
    if spec_d is None:
        raise HTTPException(400, "Treba 'spec'.")
    _, errs, size = _check(spec_d)
    return {"ok": not errs, "errors": errs, "size": size}


def _public(job, with_result=True):
    d = {k: job[k] for k in ("id", "status", "done", "total", "error", "created", "started",
                             "finished", "name")}
    if with_result and job.get("result") is not None:
        r = job["result"]
        d["result"] = sandbox.jsonable({"spec": r.spec, "points": r.points,
                                        "aggregate": r.aggregate, "meta": r.meta,
                                        "locations": r.locations})
    return d


def _worker(job, spec_d, workers):
    job["status"] = "running"
    job["started"] = time.time()

    def prog(done, total):
        job["done"], job["total"] = done, total
    try:
        res = sandbox.run(spec_d, workers=workers, progress=prog, cancel=job["cancel"])
        job["result"] = res
        job["status"] = "cancelled" if res.meta.get("cancelled") else "done"
    except Exception as e:  # noqa: BLE001 — greška se prikazuje korisniku
        job["status"] = "error"
        job["error"] = f"{type(e).__name__}: {e}"
    finally:
        job["finished"] = time.time()


@router.post("/run")
def api_run(p: dict = Body(...)):
    spec_d = p.get("spec")
    if spec_d is None and p.get("example"):
        spec_d = _example_specs().get(os.path.basename(p["example"]))
        if spec_d is None:
            raise HTTPException(404, f"Primjer ne postoji: {p['example']}")
    if spec_d is None:
        raise HTTPException(400, "Treba 'spec' ili 'example'.")
    if spec_d.get("plugins"):
        raise HTTPException(400, "Plugini nisu dopušteni preko web sučelja (pokreni sandbox.py lokalno).")
    spec, errs, size = _check(spec_d)
    if errs:
        raise HTTPException(400, {"errors": errs, "size": size})
    workers = int(min(max(int(p.get("workers", MAX_WORKERS)), 1), MAX_WORKERS, os.cpu_count() or 1))
    with _lock:
        active = [j for j in _jobs.values() if j["status"] in ("queued", "running")]
        if len(active) >= MAX_ACTIVE_JOBS:
            raise HTTPException(429, "Sandbox već vrti eksperiment — pričekaj ili ga prekini.")
        # zadrži samo zadnjih MAX_KEPT_JOBS završenih jobova
        done = sorted((j for j in _jobs.values() if j["status"] not in ("queued", "running")),
                      key=lambda j: j["created"])
        for j in done[:max(0, len(_jobs) - MAX_KEPT_JOBS + 1)]:
            _jobs.pop(j["id"], None)
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "status": "queued", "done": 0, "total": size["runs"], "error": None,
               "created": time.time(), "started": None, "finished": None,
               "name": spec.name, "cancel": threading.Event(), "result": None}
        _jobs[jid] = job
    th = threading.Thread(target=_worker, args=(job, spec_d, workers), daemon=True,
                          name=f"sandbox-{jid}")
    th.start()
    return {"job_id": jid, "size": size, "workers": workers}


def _get(jid):
    job = _jobs.get(jid)
    if job is None:
        raise HTTPException(404, "Nepoznat job.")
    return job


@router.get("/jobs/{jid}")
def api_job(jid: str):
    return _public(_get(jid))


@router.post("/jobs/{jid}/cancel")
def api_cancel(jid: str):
    job = _get(jid)
    job["cancel"].set()
    return {"ok": True, "status": job["status"]}


@router.get("/jobs/{jid}/csv")
def api_csv(jid: str, kind: str = "aggregate"):
    job = _get(jid)
    if job.get("result") is None:
        raise HTTPException(409, "Rezultat još nije spreman.")
    kind = "runs" if kind == "runs" else "aggregate"
    fname = f"sandbox_{job['name']}_{kind}.csv".replace(" ", "_")
    return PlainTextResponse(job["result"].csv_text(kind), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
