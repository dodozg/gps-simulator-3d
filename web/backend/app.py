"""FastAPI aplikacija — kontrolni centar + GPS učilište.

Uvozi postojeće engine module s roota repozitorija (dodaje ga na sys.path) i
poslužuje: WebSocket živu simulaciju, REST eksperimente i (ako je buildan)
statički frontend. Pokretanje:

    uvicorn web.backend.app:app --reload      (iz korijena repozitorija)
    ili dvoklik run_webapp.bat
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI                       # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse         # noqa: E402
from fastapi.staticfiles import StaticFiles         # noqa: E402

from web.backend.sim_session import SimSession      # noqa: E402
from web.backend.routes_sim import router as sim_router          # noqa: E402
from web.backend.routes_experiments import router as exp_router  # noqa: E402
from web.backend.routes_scenario import router as scn_router     # noqa: E402
from web.backend.routes_meta import router as meta_router        # noqa: E402

# Buildani frontend: zbog Google Drive/NTFS ograničenja build ide u lokalni dir
# (vidi build_web.bat), a putanja se prosljeđuje kroz GPSWEB_DIST. Fallback je
# web/frontend/dist ako netko builda direktno u repou.
FRONTEND_DIST = os.environ.get("GPSWEB_DIST") or os.path.join(ROOT, "web", "frontend", "dist")


def create_app():
    app = FastAPI(title="GPS Simulator 3D — Control Center & Academy", version="0.1")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    # Jedna dijeljena živa sesija (lokalni kontrolni centar, jedan korisnik).
    app.state.session = SimSession()

    app.include_router(sim_router)
    app.include_router(exp_router, prefix="/api")
    app.include_router(scn_router, prefix="/api/scenario")
    app.include_router(meta_router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "engine": "numpy", "frontend_built": os.path.isdir(FRONTEND_DIST)}

    # Buildan frontend (ako postoji) posluži kao statiku na korijenu.
    if os.path.isdir(FRONTEND_DIST):
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    else:
        @app.get("/")
        def index():
            return JSONResponse({
                "message": "Frontend nije buildan. Windows: pokreni build_web.bat. "
                           "macOS/Linux: ./build_web.sh (ili ./gps.sh web). Build ide u "
                           "lokalni dir izvan G:/ jer Google Drive nije NTFS. GPSWEB_DIST="
                           + str(FRONTEND_DIST),
                "api": "/api/health, /ws/sim, /api/rtk, /api/spoofing, /api/multignss, "
                       "/api/iono, /api/scenario/list",
            })
    return app


app = create_app()
