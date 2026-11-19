"""WebSocket živa simulacija: /ws/sim.

Klijent šalje kontrolne poruke (postavi rover, play/pause, brzina, toggles,
napad), server strimuje serijalizirano stanje ~10 puta u sekundi. Sim-vrijeme
napreduje realnim dt × time_scale kad je 'playing'.

Arhitektura: JEDNA simulacijska petlja (`SimRunner`) po aplikaciji napreduje
dijeljenu sesiju i isti frame šalje svim spojenim klijentima. Prije je svaka
veza imala vlastitu petlju koja je napredovala istu sesiju, pa su dva otvorena
taba ubrzavala simulaciju dvostruko. CPU-teški korak (FFT kanal, EKF) se vrti u
radnoj niti (`asyncio.to_thread`) da ne blokira event loop, a poruke klijenata
i korak dijele isti lock pa nikad ne mijenjaju sesiju istovremeno.
"""
import asyncio
import json
import logging
import threading
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from web.backend.serialize import state_frame

log = logging.getLogger("gpsweb.sim")

router = APIRouter()

TICK_S = 0.1              # 10 Hz stream (ciljani razmak između frameova)
MAX_WALL_DT = 0.5         # kapiraj realni dt (npr. nakon zastoja/taba u pozadini)
ACTUAL_EMA = 0.3          # izglađivanje izmjerenog ubrzanja
SEND_TIMEOUT_S = 2.0      # spor/zaglavljen klijent ne smije blokirati ostale


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
    else:
        raise ValueError(f"nepoznata poruka: {t!r}")


class SimRunner:
    """Jedna petlja koja vrti dijeljenu sesiju i emitira frame svim klijentima."""

    def __init__(self, session):
        self.session = session
        self.lock = threading.Lock()
        # klijent -> event loop u kojem živi njegova veza. Uvicorn ima jedan loop,
        # ali (npr. TestClient) svaka veza može imati vlastiti; slanje u tuđi loop
        # mora ići kroz run_coroutine_threadsafe, inače zapne.
        self.clients: dict[WebSocket, asyncio.AbstractEventLoop] = {}
        self._task: asyncio.Task | None = None

    # --- rad pod lockom (u radnoj niti) ------------------------------------
    def _tick(self, wall_dt):
        with self.lock:
            s = self.session
            if s.playing and wall_dt > 0:
                before = s.sim_time
                s.advance(wall_dt * s.time_scale)
                actual = (s.sim_time - before) / wall_dt
                prev = s.time_scale_actual
                s.time_scale_actual = actual if prev <= 0 else prev + ACTUAL_EMA * (actual - prev)
            else:
                s.time_scale_actual = 0.0
            return state_frame(s)

    def _frame(self):
        with self.lock:
            return state_frame(self.session)

    def _apply_locked(self, msg):
        with self.lock:
            _apply(self.session, msg)

    # --- javno sučelje -----------------------------------------------------
    async def frame(self):
        return await asyncio.to_thread(self._frame)

    async def apply(self, msg):
        """Primijeni poruku; neispravna poruka se logira, veza OSTAJE otvorena."""
        try:
            await asyncio.to_thread(self._apply_locked, msg)
        except Exception:
            log.warning("odbačena kontrolna poruka %r", msg, exc_info=True)

    def add_client(self, ws):
        self.clients[ws] = asyncio.get_running_loop()

    def ensure_running(self):
        t = self._task
        if t is None or t.done() or t.get_loop().is_closed():
            self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop_if_idle(self):
        t = self._task
        if self.clients or t is None or t.done():
            return
        self._task = None
        loop = t.get_loop()
        if loop is asyncio.get_running_loop():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        elif not loop.is_closed():
            loop.call_soon_threadsafe(t.cancel)

    async def _send(self, ws, loop, frame):
        coro = ws.send_json(frame)
        if loop is asyncio.get_running_loop():
            await asyncio.wait_for(coro, SEND_TIMEOUT_S)
        else:
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            await asyncio.wait_for(asyncio.wrap_future(fut), SEND_TIMEOUT_S)

    async def _loop(self):
        last = time.monotonic()
        while self.clients:
            t0 = time.monotonic()
            wall_dt = min(t0 - last, MAX_WALL_DT)
            last = t0
            try:
                frame = await asyncio.to_thread(self._tick, wall_dt)
            except Exception:
                # Greška u koraku ne smije tiho ubiti stream: zapiši je i nastavi.
                log.exception("greška u koraku simulacije")
                await asyncio.sleep(TICK_S)
                continue
            dead = []
            for ws, loop in list(self.clients.items()):
                try:
                    await self._send(ws, loop, frame)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.clients.pop(ws, None)
            await asyncio.sleep(max(0.0, TICK_S - (time.monotonic() - t0)))


def get_runner(app):
    runner = getattr(app.state, "sim_runner", None)
    if runner is None or runner.session is not app.state.session:
        runner = SimRunner(app.state.session)
        app.state.sim_runner = runner
    return runner


@router.websocket("/ws/sim")
async def ws_sim(ws: WebSocket):
    await ws.accept()
    runner = get_runner(ws.app)
    # pošalji početni frame odmah, pa se priključi zajedničkoj petlji
    await ws.send_json(await runner.frame())
    runner.add_client(ws)
    runner.ensure_running()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                log.warning("odbačena poruka koja nije JSON: %.200r", raw)
                continue
            if isinstance(msg, dict):
                await runner.apply(msg)
            else:
                log.warning("odbačena poruka koja nije objekt: %r", msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("WebSocket veza prekinuta zbog greške")
    finally:
        runner.clients.pop(ws, None)
        await runner.stop_if_idle()
