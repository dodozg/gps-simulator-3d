"""REST prave orbite: /api/orbits/* — osvježavanje GP elemenata i tragovi za globus.

- POST /refresh : skini svježe CelesTrak GP elemente u lokalni cache (mreža samo
  na izričit zahtjev korisnika); vrati status.
- GET  /status  : što je trenutno dostupno (cache/snimka, starost, broj satelita).
- GET  /tracks  : jedan ophod svakog pravog satelita u TEME okviru [m] (globus ih
  rotira s GMST-om iz framea); prazno kad sesija vrti idealizirane orbite.
"""
import asyncio
import os
import time

from fastapi import APIRouter, HTTPException, Request

import real_orbits
from web.backend.routes_sim import get_runner
from web.backend.serialize import to_jsonable

router = APIRouter()


def _status():
    data, origin = real_orbits.load_gp(allow_fetch=False)
    path = real_orbits.cache_path()
    counts = {real_orbits.GROUPS[g]: len(v) for g, v in data.get("groups", {}).items()}
    return {"origin": origin, "fetched_utc": data.get("fetched_utc"), "counts": counts,
            "cache_age_h": ((time.time() - os.path.getmtime(path)) / 3600.0
                            if os.path.isfile(path) else None)}


@router.get("/status")
async def api_status():
    return await asyncio.to_thread(_status)


@router.post("/refresh")
async def api_refresh():
    try:
        await asyncio.to_thread(real_orbits.fetch_gp)
    except Exception as e:     # mreža/servis nedostupan
        raise HTTPException(502, f"CelesTrak nedostupan: {e}") from e
    return await asyncio.to_thread(_status)


@router.get("/tracks")
async def api_tracks(request: Request):
    runner = get_runner(request.app)

    def snap():
        with runner.lock:
            con = runner.session.constellation
            if getattr(runner.session, "orbit_mode", "walker") != "real":
                return {"mode": "walker", "tracks": []}
            return to_jsonable({"mode": "real", "tracks": con.tracks(72)})

    return await asyncio.to_thread(snap)
