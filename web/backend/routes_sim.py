"""WebSocket živa simulacija: /ws/sim.

Klijent šalje kontrolne poruke (postavi rover, play/pause, brzina, toggles,
napad), server strimuje serijalizirano stanje ~10 puta u sekundi. Sim-vrijeme
napreduje realnim dt × time_scale kad je 'playing'.
"""
import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from web.backend.serialize import state_frame

router = APIRouter()

TICK_S = 0.1              # 10 Hz stream
MAX_WALL_DT = 0.25        # kapiraj realni dt (npr. nakon zastoja/taba u pozadini)


def _apply(session, msg):
    """Primijeni jednu kontrolnu poruku na sesiju."""
    t = msg.get("type")
    if t == "set_receiver":
        alt = msg.get("alt")
        session.set_receiver(float(msg["lat"]), float(msg["lon"]),
                             float(alt) if alt is not None else None)
    elif t == "play":
        session.set_playing(True)
    elif t == "pause":
        session.set_playing(False)
    elif t == "time_scale":
        session.set_time_scale(float(msg["value"]))
    elif t == "kinematic":
        session.set_kinematic(bool(msg["on"]))
    elif t == "raim":
        session.set_raim(bool(msg["on"]))
    elif t == "iono_tow0":
        session.set_iono_tow0(float(msg["value"]))
    elif t == "attack":
        session.set_attack(msg.get("spec"))
    elif t == "set_system":
        session.set_system_enabled(str(msg["system"]), bool(msg["on"]))
    elif t == "set_sat":
        session.set_sat_enabled(str(msg["id"]), bool(msg["on"]))
    elif t == "set_sat_param":
        session.set_sat_param(str(msg["id"]), str(msg["param"]), float(msg["value"]))
    elif t == "reset":
        session.reset()
    elif t == "step":
        session.advance(float(msg.get("sim_dt", 1.0)))


@router.websocket("/ws/sim")
async def ws_sim(ws: WebSocket):
    await ws.accept()
    session = ws.app.state.session
    stop = asyncio.Event()

    async def receiver_loop():
        try:
            while not stop.is_set():
                msg = await ws.receive_json()
                _apply(session, msg)
        except WebSocketDisconnect:
            stop.set()
        except Exception:
            stop.set()

    async def sender_loop():
        last = time.monotonic()
        try:
            while not stop.is_set():
                now = time.monotonic()
                wall_dt = min(now - last, MAX_WALL_DT)
                last = now
                if session.playing:
                    session.advance(wall_dt * session.time_scale)
                await ws.send_json(state_frame(session))
                await asyncio.sleep(TICK_S)
        except (WebSocketDisconnect, RuntimeError):
            stop.set()
        except Exception:
            stop.set()

    # pošalji početni frame odmah pa vrti obje petlje
    await ws.send_json(state_frame(session))
    await asyncio.gather(receiver_loop(), sender_loop())
