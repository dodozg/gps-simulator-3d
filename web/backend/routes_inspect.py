"""REST "pogled iznutra": GET /api/inspect — međuveličine zadnje epohe.

Čita dijeljenu živu sesiju pod lockom simulacijske petlje (SimRunner), pa snimka
nikad nije napola ažurirana. Teže računanje ide u radnu nit.
"""
import asyncio

from fastapi import APIRouter, Request

from web.backend.inspect_epoch import build_inspect
from web.backend.routes_sim import get_runner
from web.backend.serialize import to_jsonable

router = APIRouter()


@router.get("/inspect")
async def api_inspect(request: Request):
    runner = get_runner(request.app)

    def snap():
        with runner.lock:
            return to_jsonable(build_inspect(runner.session))

    return await asyncio.to_thread(snap)
