"""Istraživački sandbox — deklarativni eksperimenti: sweep × Monte Carlo × algoritmi.

Jedan scenarij (`scenario.py`) odgovara na pitanje "što se dogodi OVDJE, s OVIM
sjemenom". Istraživanje traži više: kako se metrika mijenja kad mijenjam parametar
(sweep), koliko je rezultat stabilan preko realizacija šuma (Monte Carlo preko
sjemena, interval pouzdanosti) i kako se usporede algoritmi na ISTIM mjerenjima.
Ovaj modul to radi iz jednog JSON opisa (spec), bez diranja enginea:

    python sandbox.py run sandbox/examples/raim_roc.json --workers 4 --out results/ --plot
    python sandbox.py validate sandbox/examples/raim_roc.json
    python sandbox.py list                    # registrirani estimatori/napadi/metrike

    import sandbox
    res = sandbox.run({"world": {"duration_s": 120}, "seeds": 5,
                       "sweep": {"attack.bias_m": [0, 20, 40]},
                       "attack": {"type": "sat_fault", "start": 30}}, workers=2)
    res.table("raim_pd")                      # numpy niz srednjih vrijednosti po točki

Spec (JSON; svi ključevi osim navedenih su greška — vidi `validate`):
    name, description
    world:     lat, lon, alt | locations [{name,lat,lon,alt}], pool_locations,
               duration_s, step_s, systems ["GPS","GAL","GLO","BDS"], constellation
               ("auto"|"walker"|"multi"), mask_deg (≥ 5), max_sats, iono_tow0,
               kinematic (false | {speed_mps, heading_deg}), terrain, ideal
    seeds:     broj (→ seed_base + i) ili lista sjemena
    sweep:     {"param": [vrijednosti], ...} — puna rešetka (ili sweep_mode "zip")
               param: attack.<x> | raim.<enabled|pfa|pmd|hal|val|sigma_scale> |
                      world.<x> ili kratko <polje svijeta> | estimator
    estimators ["ekf", "wls", ...] — svi dobiju ISTA mjerenja (uparena usporedba)
    attack:    {"type": <registrirani napad>, ...parametri} ili null
    raim:      {enabled, pfa, pmd, hal, val, sigma_scale}
    metrics:   [nazivi registriranih metrika]
    warmup_s:  epohe prije ovoga ne ulaze u metrike točnosti (konvergencija EKF-a)
    save_traces, plot ({metric, x, logx} ili lista), plugins (moduli / .py putanje)

Plugini (registri dekoratorima — istraživač dodaje kod bez diranja enginea):
    @register_estimator("ime")  factory(world) -> obj;  obj.solve(signals, t)
                                -> (pos_ecef | None, info dict); opcionalno
                                obj.estimate() -> ECEF (za DOP selekciju/tropo)
    @register_attack("ime")     factory(**params) -> obj s apply(signals, t,
                                rx_pos, rng) i is_active(t); opcionalno bind(ctx),
                                faulty_ids(t), target_ecef(rx_pos), start
    @register_metric("ime")     fn(trace) -> float  (trace = dict numpy nizova)

Determinizam: svaki run je čista funkcija (spec, točka sweepa, lokacija, sjeme) —
vlastiti np.random.Generator, RAIM konstante postavljene i vraćene unutar runa —
pa je rezultat identičan neovisno o broju workera (osim metrika vremena izvođenja,
koje su označene kao nedeterminističke).
"""
import argparse
import contextlib
import copy
import csv
import importlib
import importlib.util
import io
import itertools
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from types import SimpleNamespace

import numpy as np

import measurement
import raim
import receiver
from measurement import MeasurementModel
from physics_engine import calculate_sagnac_correction
from receiver import Receiver, SIGMA_ZENITH, MIN_SIN_ELEV
from satellite import WalkerDeltaConstellation, MultiGNSSConstellation, GNSS_SYSTEMS
from utils import lla_to_ecef, ecef_to_lla

ROOT = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_DIR = os.path.join(ROOT, "sandbox", "examples")
SPEC_VERSION = 1

ALL_SYSTEMS = ("GPS", "GAL", "GLO", "BDS")
MIN_MASK_DEG = 5.0          # mjerni model ima ugrađenu masku 5° (measurement.py) — niže nije moguće


# =============================================================================
# Registri pluginova
# =============================================================================
ESTIMATORS, ATTACKS, METRICS = {}, {}, {}


def _doc1(obj):
    d = (getattr(obj, "__doc__", None) or "").strip()
    return d.splitlines()[0] if d else ""


def register_estimator(name, description=None):
    """Dekorator: registriraj estimator `factory(world) -> obj` pod imenom `name`."""
    def deco(factory):
        ESTIMATORS[name] = SimpleNamespace(name=name, factory=factory,
                                           description=description or _doc1(factory))
        return factory
    return deco


def register_attack(name, description=None):
    """Dekorator: registriraj napad `factory(**params) -> obj` pod imenom `name`."""
    def deco(factory):
        ATTACKS[name] = SimpleNamespace(name=name, factory=factory,
                                        description=description or _doc1(factory))
        return factory
    return deco


def register_metric(name, description=None, deterministic=True, unit=""):
    """Dekorator: registriraj metriku `fn(trace) -> float` pod imenom `name`.

    deterministic=False za metrike koje ovise o stroju (npr. vrijeme izvođenja) —
    provjere determinizma ih preskaču.
    """
    def deco(fn):
        METRICS[name] = SimpleNamespace(name=name, fn=fn, deterministic=deterministic,
                                        unit=unit, description=description or _doc1(fn))
        return fn
    return deco


def load_plugins(plugins):
    """Učitaj plugin module (ime modula ili putanja do .py) — registriraju se pri importu."""
    for p in plugins or []:
        if p.endswith(".py") or os.sep in p or "/" in p:
            path = p if os.path.isabs(p) else os.path.join(os.getcwd(), p)
            modname = "sandbox_plugin_" + os.path.splitext(os.path.basename(path))[0]
            if modname in sys.modules:
                continue
            spec = importlib.util.spec_from_file_location(modname, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"plugin se ne može učitati: {p}")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[modname] = mod
            spec.loader.exec_module(mod)
        else:
            importlib.import_module(p)


# =============================================================================
# Geometrija / pomoćne funkcije
# =============================================================================
def enu_rotation(pos):
    """3×3 matrica ECEF → ENU (redci: istok, sjever, gore) u točki pos (geodetski)."""
    lat, lon, _ = ecef_to_lla(*pos)
    la, lo = math.radians(lat), math.radians(lon)
    sl, cl, sp, cp = math.sin(lo), math.cos(lo), math.sin(la), math.cos(la)
    return np.array([[-sl, cl, 0.0],
                     [-sp * cl, -sp * sl, cp],
                     [cp * cl, cp * sl, sp]])


def _sin_elev(sat_pos, rx_pos):
    up = rx_pos / max(np.linalg.norm(rx_pos), 1.0)
    v = sat_pos - rx_pos
    return float(np.dot(up, v / max(np.linalg.norm(v), 1.0)))


# =============================================================================
# Ugrađeni estimatori
# =============================================================================
@register_estimator("ekf", "EKF + dvostupanjski RAIM iz receiver.Receiver (isti kao živa simulacija)")
class EKFEstimator:
    """EKF + RAIM iz `receiver.Receiver` (11 stanja, FDE, HPL/VPL)."""

    def __init__(self, world):
        # Vlastiti mjerni model Receivera se NE koristi (mjerenja daje sandbox), pa mu
        # rng ne smije trošiti zajednički generator.
        self.rx = Receiver(np.array(world.gt0, float), rng=np.random.default_rng(0),
                           ideal=world.ideal)
        self.rx.raim_enabled = bool(world.raim["enabled"])

    def estimate(self):
        """Ista procjena koju Receiver.receive_signals predaje mjernom modelu."""
        return self.rx.x_ekf[:3].copy() if self.rx.ekf_initialized else None

    def solve(self, signals, t):
        if len(signals) < 4:
            return None, {"status": "unavailable", "n_used": len(signals)}
        m = self.rx.meas
        m.received_signals = signals
        m.last_update_time = t
        pos, gdop = self.rx.solve_position()
        integ = dict(self.rx.integrity)
        integ.pop("normalized", None)
        info = {"integrity": integ, "status": integ.get("status"),
                "excluded": list(integ.get("excluded", []) or []),
                "alarm": bool(self.rx.raim_alarm), "raim_alarm": self.rx.raim_alarm,
                "gdop": gdop, "n_used": len(signals)}
        if pos is not None:
            info.update(hpl=integ.get("hpl"), vpl=integ.get("vpl"),
                        nis=self.rx.nis, nis_dof=self.rx.nis_dof)
            pos = np.array(pos, float)
        return pos, info


@register_estimator("wls", "snapshot težinski najmanji kvadrati + snapshot RAIM (FDE, HPL/VPL)")
class WLSEstimator:
    """Snapshot WLS (Gauss-Newton) s jednim satom po sustavu i snapshot RAIM-om.

    Model mjerenja je isti kao u EKF-u (receiver.py): ρ = |x − s_broadcast| +
    Sagnac(s, x) + c·dt_sustava. Jedan stupac sata po sustavu prisutnom u
    mjerenjima upija i inter-system bias (GPS sat + ISB razapinju isti prostor),
    pa je rješenje nepristrano i za multi-GNSS. Težine: σ(el) = SIGMA_ZENITH/sin(el).
    """

    MAX_ITER = 20

    def __init__(self, world):
        self.raim_cfg = dict(world.raim)
        self.pos = None

    def estimate(self):
        return None if self.pos is None else self.pos.copy()

    def _solve(self, signals, x0):
        systems = sorted({s.get("system", "GPS") for s in signals})
        col = {s: 3 + k for k, s in enumerate(systems)}
        n, m = len(signals), 3 + len(systems)
        if n < m:
            return None
        sats = np.array([s["broadcast_pos"] for s in signals], float)
        pr = np.array([s["pseudorange"] for s in signals], float)
        x = np.zeros(m)
        if x0 is not None:
            x[:3] = x0
        G = np.zeros((n, m))
        for k, s in enumerate(signals):
            G[k, col[s.get("system", "GPS")]] = 1.0
        sigma = np.ones(n)
        for it in range(self.MAX_ITER):
            pos = x[:3]
            diff = pos - sats
            rng_ = np.maximum(np.linalg.norm(diff, axis=1), 1.0)
            sag = np.array([calculate_sagnac_correction(sp, pos) for sp in sats])
            clk = G[:, 3:] @ x[3:]
            resid = pr - (rng_ + sag + clk)
            G[:, :3] = diff / rng_[:, None]
            if np.linalg.norm(pos) > 6.0e6:       # elevacije imaju smisla tek blizu Zemlje
                sin_el = np.array([max(_sin_elev(sp, pos), MIN_SIN_ELEV) for sp in sats])
                sigma = SIGMA_ZENITH / sin_el
            w = 1.0 / sigma ** 2
            GW = G.T * w
            try:
                dx = np.linalg.solve(GW @ G, GW @ resid)
            except np.linalg.LinAlgError:
                return None
            x = x + dx
            if np.linalg.norm(dx[:3]) < 1e-4 and it > 0:
                break
        # konačni reziduali u rješenju
        pos = x[:3]
        diff = pos - sats
        rng_ = np.maximum(np.linalg.norm(diff, axis=1), 1.0)
        sag = np.array([calculate_sagnac_correction(sp, pos) for sp in sats])
        resid = pr - (rng_ + sag + G[:, 3:] @ x[3:])
        G[:, :3] = diff / rng_[:, None]
        if not np.all(np.isfinite(x)):
            return None
        return SimpleNamespace(x=x, G=G.copy(), resid=resid, sigma=sigma.copy(), n=n, m=m)

    def solve(self, signals, t):
        sol = self._solve(signals, self.pos)
        if sol is None:
            return None, {"status": "unavailable", "n_used": len(signals)}
        info = {"status": "disabled", "excluded": [], "alarm": False, "n_used": sol.n}
        if self.raim_cfg.get("enabled", True):
            scale = float(self.raim_cfg.get("sigma_scale", receiver.RAIM_SIGMA_SCALE))
            res = raim.run_raim(sol.G, sol.resid, sol.sigma * scale, sol.x[:3],
                                pfa=self.raim_cfg["pfa"], pmd=self.raim_cfg["pmd"],
                                hal=self.raim_cfg["hal"], val=self.raim_cfg.get("val"))
            excluded = sorted(res["excluded"])
            if excluded:
                keep = [s for i, s in enumerate(signals) if i not in set(excluded)]
                sol2 = self._solve(keep, sol.x[:3])
                if sol2 is not None:
                    sol = sol2
            info.update(status=res["status"], hpl=res["hpl"], vpl=res["vpl"],
                        test=res["test"], threshold=res["threshold"],
                        excluded=[signals[i]["sat_id"] for i in excluded],
                        alarm=res["status"] in ("alarm", "excluded"), n_used=sol.n)
        dof = sol.n - sol.m
        w = 1.0 / sol.sigma ** 2
        if dof > 0:
            info.update(nis=float(np.sum(w * sol.resid ** 2)), nis_dof=dof)
        try:
            Q = np.linalg.inv(sol.G.T @ sol.G)
            info["gdop"] = float(np.sqrt(np.trace(Q)))
        except np.linalg.LinAlgError:
            info["gdop"] = None
        self.pos = sol.x[:3].copy()
        return self.pos.copy(), info


# =============================================================================
# Ugrađeni napadi
# =============================================================================
def _builtin_attack(kind):
    def factory(**params):
        from scenario import build_attack      # lijeni import: spoofing.py se paralelno razvija
        return build_attack({"type": kind, **params})
    factory.__doc__ = f"spoofing.py napad '{kind}' (preko scenario.build_attack)"
    return factory


for _kind, _desc in (("coordinated", "koordinirani spoof (seamless takeover): offset_e/n/u, start, end"),
                     ("naive", "naivni multi-SV spoof: n, bias_m, start, end"),
                     ("meaconing", "uniformni meaconing: delay_m, start, end"),
                     ("jamming", "ometanje: js_db (J/N), start, end")):
    register_attack(_kind, _desc)(_builtin_attack(_kind))


@register_attack("sat_fault", "kvar sata jednog satelita (korak ili rampa): bias_m, rate_mps, start, stop, sat_id, ramp_s")
class SatClockFault:
    """Kvar sata satelita: pseudoudaljenost jednog satelita dobije pomak.

    bias_m: iznos koraka [m]; rate_mps: dodatni linearni rast [m/s] (spori kvar);
    ramp_s: trajanje rampe do bias_m (0 = trenutni korak); start/stop: aktivni
    interval (stop=None → do kraja). Satelit: sat_id, ili nasumičan među praćenima
    u prvoj aktivnoj epohi (vlastiti RNG iz sjemena runa — ne troši zajednički
    generator, pa runovi s različitim bias_m vide ISTI šum i isti satelit).
    """
    name = "sat_fault"

    def __init__(self, bias_m=50.0, rate_mps=0.0, start=60.0, stop=None, ramp_s=0.0,
                 sat_id=None, end=None):
        self.bias_m, self.rate_mps = float(bias_m), float(rate_mps)
        self.start = float(start)
        self.stop = None if stop is None else float(stop)
        self.end = self.start + float(ramp_s)     # kraj rampe (kompatibilno sa spoofing.Attack)
        self.ramp_s = float(ramp_s)
        self.sat_id = sat_id
        self._pick_rng = np.random.default_rng(0)
        self.desc = f"kvar sata satelita {sat_id or '(nasumičan)'}: {bias_m:g} m + {rate_mps:g} m/s od t={start:g} s"

    def bind(self, ctx):
        self._pick_rng = np.random.default_rng([int(ctx.seed), 0x5A7F])

    def is_active(self, t):
        return t >= self.start and (self.stop is None or t <= self.stop)

    def faulty_ids(self, t):
        return [self.sat_id] if (self.sat_id and self.is_active(t)) else []

    def apply(self, signals, t, rx_pos, rng):
        if not self.is_active(t) or not signals:
            return
        if self.sat_id is None:
            ids = sorted(s["sat_id"] for s in signals)
            self.sat_id = ids[int(self._pick_rng.integers(len(ids)))]
        f = 1.0 if self.ramp_s <= 0 else min(1.0, (t - self.start) / self.ramp_s)
        bias = self.bias_m * f + self.rate_mps * (t - self.start)
        for s in signals:
            if s["sat_id"] == self.sat_id:
                s["pseudorange"] += bias


# =============================================================================
# Ugrađene metrike (nad tragom po epohama)
# =============================================================================
# trace: dict numpy nizova duljine N epoha + trace["meta"] (dict):
#   t, fix (bool), err_h, err_v, err_3d (NaN bez fixa), hpl, vpl (NaN = nema),
#   detect (RAIM detekcija/isključenje), excluded_n, faulty_excluded, fault_present
#   (pokvareni satelit je u mjerenjima), attack_active,
#   n_sats, nis_norm (NIS/dof), gdop, runtime_s, target_dist
#   meta: hal, val, warmup_s, has_attack, attack_start, has_faulty, estimator
def _acc_mask(tr):
    return tr["fix"] & (tr["t"] >= tr["meta"]["warmup_s"])


def _stat(fn, arr):
    arr = arr[np.isfinite(arr)]
    return float(fn(arr)) if len(arr) else float("nan")


_STATS = {
    "mean": np.mean, "median": np.median, "max": np.max,
    "p95": lambda a: np.percentile(a, 95),
    "rms": lambda a: np.sqrt(np.mean(a ** 2)),
}
for _comp, _key, _lab in (("h", "err_h", "horizontalna"), ("v", "err_v", "vertikalna"),
                          ("3d", "err_3d", "3D")):
    for _sn, _sf in _STATS.items():
        _name = f"err{_comp}_{_sn}" if _comp == "3d" else f"{_comp}_err_{_sn}"

        def _mk(key=_key, sf=_sf):
            return lambda tr: _stat(sf, tr[key][_acc_mask(tr)])
        register_metric(_name, f"{_lab} greška [m], {_sn} (epohe s fixom nakon warmup_s)",
                        unit="m")(_mk())


@register_metric("availability", "udio epoha s fixom (sve epohe)")
def m_availability(tr):
    return float(np.mean(tr["fix"])) if len(tr["fix"]) else float("nan")


@register_metric("win_availability", "udio epoha s fixom dok je napad aktivan")
def m_win_availability(tr):
    w = tr["attack_active"]
    return float(np.mean(tr["fix"][w])) if w.any() else float("nan")


@register_metric("integrity_availability", "udio epoha s fixom i HPL ≤ HAL (i VPL ≤ VAL ako je zadan)")
def m_integrity_availability(tr):
    if not len(tr["fix"]):
        return float("nan")
    ok = tr["fix"] & np.isfinite(tr["hpl"]) & (np.nan_to_num(tr["hpl"], nan=np.inf) <= tr["meta"]["hal"])
    val = tr["meta"].get("val")
    if val is not None:
        ok &= np.nan_to_num(tr["vpl"], nan=np.inf) <= val
    return float(np.mean(ok))


def _post_warmup(tr):
    return tr["t"] >= tr["meta"]["warmup_s"]


@register_metric("raim_detections", "broj epoha s RAIM detekcijom/isključenjem dok je napad aktivan")
def m_raim_detections(tr):
    return float(np.sum(tr["detect"] & tr["attack_active"]))


def _fault_epochs(tr):
    """Epohe u kojima kvar stvarno djeluje: napad aktivan i (ako napad imenuje
    pokvarene satelite) barem jedan od njih je u mjerenjima."""
    w = tr["attack_active"].copy()
    if tr["meta"]["has_faulty"]:
        w &= tr["fault_present"]
    return w


@register_metric("raim_pd", "vjerojatnost detekcije po epohi dok kvar djeluje (pokvareni satelit u mjerenjima)")
def m_raim_pd(tr):
    w = _fault_epochs(tr)
    return float(np.mean(tr["detect"][w])) if w.any() else float("nan")


@register_metric("raim_detected", "1 ako je RAIM barem jednom detektirao za napada, inače 0")
def m_raim_detected(tr):
    if not tr["meta"]["has_attack"]:
        return float("nan")
    return float(np.any(tr["detect"] & tr["attack_active"]))


@register_metric("raim_exclusions", "broj epoha u kojima je isključen barem jedan satelit, za napada")
def m_raim_exclusions(tr):
    return float(np.sum((tr["excluded_n"] > 0) & tr["attack_active"]))


@register_metric("correct_exclusion_rate", "udio aktivnih epoha napada u kojima je isključen BAŠ pokvareni satelit")
def m_correct_exclusion(tr):
    w = _fault_epochs(tr)
    if not tr["meta"]["has_faulty"] or not w.any():
        return float("nan")
    return float(np.mean(tr["faulty_excluded"][w]))


@register_metric("false_alarms", "broj epoha s RAIM detekcijom izvan napada (nakon warmup_s)")
def m_false_alarms(tr):
    return float(np.sum(tr["detect"] & ~tr["attack_active"] & _post_warmup(tr)))


@register_metric("false_alarm_rate", "lažni alarmi / epohe bez napada (nakon warmup_s)")
def m_false_alarm_rate(tr):
    w = ~tr["attack_active"] & _post_warmup(tr) & tr["fix"]
    return float(np.mean(tr["detect"][w])) if w.any() else float("nan")


@register_metric("time_to_detect", "vrijeme od starta napada do prve detekcije [s] (NaN = nije detektirano)", unit="s")
def m_time_to_detect(tr):
    st = tr["meta"].get("attack_start")
    w = tr["detect"] & tr["attack_active"]
    if st is None or not w.any():
        return float("nan")
    return float(tr["t"][np.argmax(w)] - st)


@register_metric("hpl_max", "najveći HPL [m]", unit="m")
def m_hpl_max(tr):
    return _stat(np.max, tr["hpl"][_post_warmup(tr)])


@register_metric("hpl_median", "medijan HPL-a [m]", unit="m")
def m_hpl_median(tr):
    return _stat(np.median, tr["hpl"][_post_warmup(tr)])


@register_metric("vpl_median", "medijan VPL-a [m]", unit="m")
def m_vpl_median(tr):
    return _stat(np.median, tr["vpl"][_post_warmup(tr)])


def _mi(tr):
    w = tr["fix"] & np.isfinite(tr["hpl"]) & _post_warmup(tr)
    return w, w & (tr["err_h"] > tr["hpl"])


@register_metric("mi_events", "misleading information: epohe s greškom > HPL (bez alarma koji ga pokriva)")
def m_mi_events(tr):
    _, mi = _mi(tr)
    return float(np.sum(mi & ~tr["detect"]))


@register_metric("mi_rate", "udio epoha s HPL-om u kojima je horizontalna greška > HPL i nema alarma")
def m_mi_rate(tr):
    w, mi = _mi(tr)
    return float(np.sum(mi & ~tr["detect"]) / np.sum(w)) if w.any() else float("nan")


@register_metric("hmi_events", "hazardously misleading: greška > HAL, a HPL ≤ HAL i nema alarma")
def m_hmi_events(tr):
    w = tr["fix"] & np.isfinite(tr["hpl"]) & _post_warmup(tr) & ~tr["detect"]
    hal = tr["meta"]["hal"]
    return float(np.sum(w & (tr["err_h"] > hal) & (tr["hpl"] <= hal)))


@register_metric("fix_loss_count", "broj gubitaka fixa (prijelaz fix → bez fixa)")
def m_fix_loss(tr):
    f = tr["fix"].astype(int)
    return float(np.sum((f[:-1] == 1) & (f[1:] == 0))) if len(f) > 1 else 0.0


@register_metric("no_fix_epochs", "broj epoha bez fixa")
def m_no_fix(tr):
    return float(np.sum(~tr["fix"]))


@register_metric("nis_mean", "srednji NIS/dof (EKF: inovacije; WLS: χ²/redundancija) — konzistentno ≈ 1")
def m_nis(tr):
    return _stat(np.mean, tr["nis_norm"][_post_warmup(tr)])


@register_metric("gdop_median", "medijan GDOP-a")
def m_gdop(tr):
    return _stat(np.median, tr["gdop"][_post_warmup(tr)])


@register_metric("n_sats_mean", "srednji broj mjerenja (satelita) po epohi")
def m_nsats(tr):
    return float(np.mean(tr["n_sats"])) if len(tr["n_sats"]) else float("nan")


@register_metric("final_err", "medijan 3D greške u zadnjih 10 epoha s fixom [m]", unit="m")
def m_final_err(tr):
    e = tr["err_3d"][tr["fix"]]
    return float(np.median(e[-10:])) if len(e) else float("nan")


@register_metric("win_err_median", "medijan 3D greške dok je napad aktivan [m]", unit="m")
def m_win_err(tr):
    w = tr["fix"] & tr["attack_active"]
    return _stat(np.median, tr["err_3d"][w])


@register_metric("takeover_m", "udaljenost rješenja od cilja spoofa, medijan zadnjih 10 epoha [m]", unit="m")
def m_takeover(tr):
    d = tr["target_dist"][np.isfinite(tr["target_dist"])]
    return float(np.median(d[-10:])) if len(d) else float("nan")


@register_metric("runtime_ms", "srednje vrijeme solvera po epohi [ms] (ovisi o stroju)",
                 deterministic=False, unit="ms")
def m_runtime(tr):
    return float(np.mean(tr["runtime_s"]) * 1e3) if len(tr["runtime_s"]) else float("nan")


DEFAULT_METRICS = ["availability", "h_err_median", "h_err_p95", "v_err_p95", "err3d_median",
                   "integrity_availability", "hpl_median", "mi_events", "raim_detections",
                   "false_alarms", "fix_loss_count", "nis_mean", "runtime_ms"]


# =============================================================================
# Spec
# =============================================================================
@dataclass
class World:
    lat: float = 45.815
    lon: float = 15.982
    alt: float = 120.0
    locations: list = None            # [{name, lat, lon, alt}] — nadjačava lat/lon/alt
    pool_locations: bool = False      # True: lokacije su Monte Carlo replike (s sjemenima)
    duration_s: float = 300.0
    step_s: float = 1.0
    systems: list = field(default_factory=lambda: ["GPS"])
    constellation: str = "auto"       # auto: samo GPS → Walker (kao scenario.py), inače multi
    mask_deg: float = 5.0
    max_sats: int = 10
    iono_tow0: float = 50400.0
    kinematic: object = False         # False | {"speed_mps": .., "heading_deg": ..}
    terrain: bool = True              # LOS raycasting kroz DEM (sporije; False = bez terena)
    ideal: bool = False               # zero-noise mod (tests/test_consistency.py)


@dataclass
class Spec:
    name: str = "eksperiment"
    description: str = ""
    world: dict = field(default_factory=dict)
    seeds: object = 3
    seed_base: int = 1000
    sweep: dict = field(default_factory=dict)
    sweep_mode: str = "grid"
    estimators: list = field(default_factory=lambda: ["ekf"])
    attack: dict = None
    raim: dict = field(default_factory=dict)
    metrics: list = field(default_factory=lambda: list(DEFAULT_METRICS))
    warmup_s: float = 30.0
    save_traces: bool = False
    plot: object = None
    plugins: list = field(default_factory=list)
    version: int = SPEC_VERSION


WORLD_FIELDS = set(World.__dataclass_fields__)
SPEC_FIELDS = set(Spec.__dataclass_fields__)
RAIM_FIELDS = {"enabled", "pfa", "pmd", "hal", "val", "sigma_scale"}


def _raim_defaults():
    return {"enabled": True, "pfa": raim.RAIM_PFA, "pmd": raim.RAIM_PMD,
            "hal": raim.RAIM_HAL, "val": raim.RAIM_VAL,
            "sigma_scale": receiver.RAIM_SIGMA_SCALE}


class SpecError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _seed_list(spec):
    s = spec.seeds
    if isinstance(s, bool):
        raise SpecError(["seeds: broj ili lista cijelih brojeva"])
    if isinstance(s, int):
        return [spec.seed_base + i for i in range(s)]
    return [int(x) for x in s]


def _set_path(d, path, value):
    parts = path.split(".")
    for p in parts[:-1]:
        if not isinstance(d.get(p), dict):
            d[p] = {}
        d = d[p]
    d[parts[-1]] = value


def _sweep_target(key):
    """Mapiraj ključ sweepa na (sekcija, putanja) ili None ako je nepoznat."""
    if key == "estimator":
        return ("estimator", None)
    head, _, rest = key.partition(".")
    if head in ("world", "raim", "attack") and rest:
        return (head, rest)
    if head in WORLD_FIELDS:
        return ("world", key)
    return None


def _sweep_points(spec):
    keys = list(spec.sweep.keys())
    vals = [list(spec.sweep[k]) for k in keys]
    if not keys:
        return [{}]
    if spec.sweep_mode == "zip":
        n = len(vals[0])
        return [dict(zip(keys, [v[i] for v in vals])) for i in range(n)]
    return [dict(zip(keys, combo)) for combo in itertools.product(*vals)]


def _locations(world):
    if world.get("locations"):
        out = []
        for i, loc in enumerate(world["locations"]):
            out.append({"name": str(loc.get("name", f"loc{i}")), "lat": float(loc["lat"]),
                        "lon": float(loc["lon"]), "alt": float(loc.get("alt", 0.0))})
        return out
    return [{"name": "default", "lat": float(world.get("lat", World.lat)),
             "lon": float(world.get("lon", World.lon)), "alt": float(world.get("alt", World.alt))}]


def resolve_config(spec, params, location):
    """Konkretna konfiguracija jednog runa: (world, raim, attack, estimators)."""
    world = asdict(World())
    world.update(copy.deepcopy(spec.world))
    rcfg = _raim_defaults()
    rcfg.update(copy.deepcopy(spec.raim))
    attack = copy.deepcopy(spec.attack) if spec.attack else None
    estimators = list(spec.estimators)
    for key, v in params.items():
        sec, path = _sweep_target(key)
        if sec == "estimator":
            estimators = [v]
        elif sec == "world":
            _set_path(world, path, copy.deepcopy(v))
        elif sec == "raim":
            _set_path(rcfg, path, v)
        elif sec == "attack":
            if attack is None:
                attack = {}
            _set_path(attack, path, copy.deepcopy(v))
    world.update({"lat": location["lat"], "lon": location["lon"], "alt": location["alt"]})
    if attack is not None and not attack.get("type"):
        attack = None
    return world, rcfg, attack, estimators


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _check_world(w, errs, where=""):
    for k in w:
        if k not in WORLD_FIELDS:
            errs.append(f"{where}world: nepoznat ključ '{k}'")
    for k in ("lat", "lon", "alt", "duration_s", "step_s", "mask_deg", "iono_tow0"):
        if k in w and not _num(w[k]):
            errs.append(f"{where}world.{k}: mora biti broj")
    if _num(w.get("lat", 0)) and not -90 <= w.get("lat", 0) <= 90:
        errs.append(f"{where}world.lat izvan [-90, 90]")
    if _num(w.get("duration_s", 1)) and not 1 <= w.get("duration_s", 1) <= 86400:
        errs.append(f"{where}world.duration_s izvan [1, 86400]")
    if _num(w.get("step_s", 1)) and not 0.1 <= w.get("step_s", 1) <= 3600:
        errs.append(f"{where}world.step_s izvan [0.1, 3600]")
    if _num(w.get("mask_deg", 5)) and not MIN_MASK_DEG <= w.get("mask_deg", 5) <= 80:
        errs.append(f"{where}world.mask_deg izvan [{MIN_MASK_DEG:g}, 80] (mjerni model ima ugrađenu masku 5°)")
    ms = w.get("max_sats", 10)
    if isinstance(ms, bool) or not isinstance(ms, int) or not 4 <= ms <= 40:
        errs.append(f"{where}world.max_sats: cijeli broj u [4, 40]")
    sysl = w.get("systems", ["GPS"])
    if not isinstance(sysl, list) or not sysl or any(s not in ALL_SYSTEMS for s in sysl):
        errs.append(f"{where}world.systems: neprazna lista iz {list(ALL_SYSTEMS)}")
    con = w.get("constellation", "auto")
    if con not in ("auto", "walker", "multi"):
        errs.append(f"{where}world.constellation: 'auto' | 'walker' | 'multi'")
    elif con == "walker" and isinstance(sysl, list) and sysl != ["GPS"]:
        errs.append(f"{where}world.constellation='walker' podržava samo systems=['GPS']")
    kin = w.get("kinematic", False)
    if kin not in (False, None, True) and not isinstance(kin, dict):
        errs.append(f"{where}world.kinematic: false ili {{speed_mps, heading_deg}}")
    if isinstance(kin, dict):
        for k in kin:
            if k not in ("speed_mps", "heading_deg"):
                errs.append(f"{where}world.kinematic: nepoznat ključ '{k}'")
            elif not _num(kin[k]):
                errs.append(f"{where}world.kinematic.{k}: mora biti broj")
    if w.get("locations") is not None:
        locs = w["locations"]
        if not isinstance(locs, list) or not locs:
            errs.append(f"{where}world.locations: neprazna lista")
        else:
            for i, loc in enumerate(locs):
                if not isinstance(loc, dict) or not _num(loc.get("lat")) or not _num(loc.get("lon")):
                    errs.append(f"{where}world.locations[{i}]: treba {{lat, lon[, alt, name]}}")


def _check_raim(r, errs, where=""):
    for k in r:
        if k not in RAIM_FIELDS:
            errs.append(f"{where}raim: nepoznat ključ '{k}'")
    if "enabled" in r and not isinstance(r["enabled"], bool):
        errs.append(f"{where}raim.enabled: true/false")
    for k in ("pfa", "pmd"):
        if k in r and (not _num(r[k]) or not 0 < r[k] < 0.5):
            errs.append(f"{where}raim.{k}: vjerojatnost u (0, 0.5)")
    if "hal" in r and (not _num(r["hal"]) or r["hal"] <= 0):
        errs.append(f"{where}raim.hal: pozitivan broj [m]")
    if r.get("val") is not None and (not _num(r["val"]) or r["val"] <= 0):
        errs.append(f"{where}raim.val: pozitivan broj [m] ili null")
    if "sigma_scale" in r and (not _num(r["sigma_scale"]) or not 0.1 <= r["sigma_scale"] <= 20):
        errs.append(f"{where}raim.sigma_scale: broj u [0.1, 20]")


def _check_attack(a, errs, where=""):
    if a is None:
        return
    if not isinstance(a, dict):
        errs.append(f"{where}attack: objekt {{type, ...}} ili null")
        return
    if a.get("type") not in ATTACKS:
        errs.append(f"{where}attack.type: '{a.get('type')}' nije registriran ({sorted(ATTACKS)})")
        return
    params = {k: v for k, v in a.items() if k != "type"}
    try:
        ATTACKS[a["type"]].factory(**params)
    except TypeError as e:
        errs.append(f"{where}attack '{a['type']}': neispravni parametri ({e})")
    except Exception as e:  # noqa: BLE001 — poruka plugina ide korisniku
        errs.append(f"{where}attack '{a['type']}': {e}")


def parse_spec(d):
    """dict → Spec (bez provjere vrijednosti). Nepoznati ključevi → SpecError."""
    if isinstance(d, Spec):
        return d
    if not isinstance(d, dict):
        raise SpecError(["spec mora biti JSON objekt"])
    unknown = [k for k in d if k not in SPEC_FIELDS]
    if unknown:
        raise SpecError([f"nepoznat ključ speca: '{k}'" for k in unknown])
    return Spec(**copy.deepcopy(d))


def validate(d, max_points=100000):
    """Provjeri spec. Vrati (Spec | None, lista grešaka). Učitava navedene plugine."""
    errs = []
    try:
        spec = parse_spec(d)
    except SpecError as e:
        return None, e.errors
    try:
        load_plugins(spec.plugins)
    except Exception as e:  # noqa: BLE001
        errs.append(f"plugins: {e}")
    if not isinstance(spec.world, dict):
        return None, ["world: mora biti objekt"]
    if not isinstance(spec.raim, dict):
        return None, ["raim: mora biti objekt"]
    if not isinstance(spec.sweep, dict):
        return None, ["sweep: mora biti objekt {param: [vrijednosti]}"]
    _check_world(spec.world, errs)
    _check_raim(spec.raim, errs)
    _check_attack(spec.attack, errs)
    try:
        seeds = _seed_list(spec)
        if not seeds:
            errs.append("seeds: barem jedno sjeme")
        if len(set(seeds)) != len(seeds):
            errs.append("seeds: sjemena se ponavljaju")
    except (SpecError, TypeError, ValueError):
        errs.append("seeds: broj ili lista cijelih brojeva")
    if not isinstance(spec.estimators, list) or not spec.estimators:
        errs.append("estimators: neprazna lista")
    else:
        for e in spec.estimators:
            if e not in ESTIMATORS:
                errs.append(f"estimators: '{e}' nije registriran ({sorted(ESTIMATORS)})")
    if not isinstance(spec.metrics, list) or not spec.metrics:
        errs.append("metrics: neprazna lista")
    else:
        for m in spec.metrics:
            if m not in METRICS:
                errs.append(f"metrics: '{m}' nije registrirana")
    if spec.sweep_mode not in ("grid", "zip"):
        errs.append("sweep_mode: 'grid' ili 'zip'")
    if not _num(spec.warmup_s) or spec.warmup_s < 0:
        errs.append("warmup_s: nenegativan broj")
    for k, v in spec.sweep.items():
        if _sweep_target(k) is None:
            errs.append(f"sweep: nepoznat parametar '{k}' (attack.*, raim.*, world.*, polje svijeta ili 'estimator')")
        elif not isinstance(v, list) or not v:
            errs.append(f"sweep.{k}: neprazna lista vrijednosti")
        elif k == "estimator":
            for e in v:
                if e not in ESTIMATORS:
                    errs.append(f"sweep.estimator: '{e}' nije registriran")
    if spec.sweep_mode == "zip" and spec.sweep:
        lens = {len(v) for v in spec.sweep.values() if isinstance(v, list)}
        if len(lens) > 1:
            errs.append("sweep_mode 'zip': sve liste moraju biti iste duljine")
    if errs:
        return None, errs
    # provjera svake točke sweepa (vrijednosti mogu biti izvan raspona)
    points = _sweep_points(spec)
    if len(points) > max_points:
        return None, [f"sweep: {len(points)} točaka > {max_points}"]
    seen = set()
    for p in points:
        for loc in _locations(spec.world):
            world, rcfg, attack, _ = resolve_config(spec, p, loc)
            perr = []
            _check_world(world, perr)
            _check_raim(rcfg, perr)
            akey = json.dumps(attack, sort_keys=True, default=str)
            if akey not in seen:
                seen.add(akey)
                _check_attack(attack, perr)
            if perr:
                lab = ", ".join(f"{k}={v}" for k, v in p.items())
                errs.extend(f"[{lab}] {e}" for e in perr)
        if len(errs) > 20:
            errs.append("…")
            break
    return (None if errs else spec), errs


def plan_size(spec):
    """Broj runova i ukupno epoha × estimatora (za ograničenja servera)."""
    spec = parse_spec(spec)
    pts = _sweep_points(spec)
    locs = _locations(spec.world)
    seeds = _seed_list(spec)
    n_runs = len(pts) * len(locs) * len(seeds)
    epochs = 0
    for p in pts:
        world, _, _, ests = resolve_config(spec, p, locs[0])
        epochs += int(world["duration_s"] / world["step_s"]) * len(ests) * len(locs) * len(seeds)
    return {"points": len(pts), "locations": len(locs), "seeds": len(seeds),
            "runs": n_runs, "epochs": epochs}


# =============================================================================
# Jedan run (čista funkcija — izvodi se i u worker procesima)
# =============================================================================
class _SandboxMeasurement(MeasurementModel):
    """MeasurementModel s opcionalnim isključenjem terena (LOS kroz DEM je skup)."""

    def __init__(self, pos, rng, ideal, terrain):
        super().__init__(pos, rng, ideal)
        self._terrain = terrain

    def check_los(self, sat_pos, rec_pos):
        return super().check_los(sat_pos, rec_pos) if self._terrain else True


@contextlib.contextmanager
def engine_settings(rcfg, max_sats):
    """Postavi modulske konstante RAIM-a/mjernog modela za jedan run i VRATI ih.

    raim.run_raim ima zadane argumente vezane pri definiciji (pfa=RAIM_PFA...), pa
    sama promjena konstante ne bi djelovala na receiver.py — zato se za trajanje
    runa run_raim omota da čita trenutne vrijednosti. receiver.py se ne mijenja.
    """
    saved = (raim.RAIM_PFA, raim.RAIM_PMD, raim.RAIM_HAL, raim.RAIM_VAL,
             receiver.RAIM_SIGMA_SCALE, measurement.MAX_SATS, raim.run_raim)
    orig_run = raim.run_raim

    def _run_raim(G, y, sigma, pos, ids=None, pfa=None, pmd=None, hal=None, val=None,
                  exclude=True):
        return orig_run(G, y, sigma, pos, ids=ids,
                        pfa=raim.RAIM_PFA if pfa is None else pfa,
                        pmd=raim.RAIM_PMD if pmd is None else pmd,
                        hal=raim.RAIM_HAL if hal is None else hal,
                        val=raim.RAIM_VAL if val is None else val, exclude=exclude)
    try:
        raim.RAIM_PFA = float(rcfg["pfa"])
        raim.RAIM_PMD = float(rcfg["pmd"])
        raim.RAIM_HAL = float(rcfg["hal"])
        raim.RAIM_VAL = None if rcfg.get("val") is None else float(rcfg["val"])
        receiver.RAIM_SIGMA_SCALE = float(rcfg["sigma_scale"])
        measurement.MAX_SATS = int(max_sats)
        raim.run_raim = _run_raim
        yield
    finally:
        (raim.RAIM_PFA, raim.RAIM_PMD, raim.RAIM_HAL, raim.RAIM_VAL,
         receiver.RAIM_SIGMA_SCALE, measurement.MAX_SATS, raim.run_raim) = saved


def _build_constellation(world, rng):
    systems = list(world["systems"])
    kind = world.get("constellation", "auto")
    if kind == "walker" or (kind == "auto" and systems == ["GPS"]):
        con = WalkerDeltaConstellation(rng=rng)
    else:
        con = MultiGNSSConstellation(systems=tuple(s for s in ALL_SYSTEMS if s in systems), rng=rng)
    for s in con.satellites:
        s.is_spoofed = False          # kvarove definira spec (napad), ne ugrađeni demo
    return con


def _trajectory(world):
    gt0 = np.array(lla_to_ecef(world["lat"], world["lon"], world["alt"]))
    kin = world.get("kinematic")
    if not kin:
        return lambda t: gt0
    if kin is True:
        kin = {}
    v = float(kin.get("speed_mps", 20.0))
    hdg = math.radians(float(kin.get("heading_deg", 90.0)))
    R = enu_rotation(gt0)
    d_enu = np.array([math.sin(hdg), math.cos(hdg), 0.0])
    d_ecef = R.T @ d_enu
    alt = world["alt"]

    def traj(t):
        p = gt0 + d_ecef * v * t
        lat, lon, _ = ecef_to_lla(*p)
        return np.array(lla_to_ecef(lat, lon, alt))     # stalna visina (let po elipsoidu)
    return traj


class _View:
    """Pogled na konstelaciju: samo sateliti dopuštenih sustava iznad maske."""
    __slots__ = ("satellites",)

    def __init__(self, sats):
        self.satellites = sats


def _visible_view(con, gt, world):
    systems = set(world["systems"])
    mask = float(world["mask_deg"])
    sats = [s for s in con.satellites if s.system in systems]
    if mask > MIN_MASK_DEG:
        up = gt / np.linalg.norm(gt)
        keep = []
        for s in sats:
            v = s.current_pos - gt
            el = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(up, v / np.linalg.norm(v)))))))
            if el >= mask:
                keep.append(s)
        sats = keep
    return _View(sats)


_TRACE_KEYS = ("t", "fix", "err_h", "err_v", "err_3d", "hpl", "vpl", "detect", "excluded_n",
               "faulty_excluded", "fault_present", "attack_active", "n_sats", "nis_norm", "gdop", "runtime_s",
               "target_dist")


def _f(x):
    return float("nan") if x is None else float(x)


def simulate(spec, params, location, seed):
    """Odvrti jedan run. Vrati {estimator: trace} (trace = dict numpy nizova + meta)."""
    spec = parse_spec(spec)
    world, rcfg, attack_spec, est_names = resolve_config(spec, params, location)
    rng = np.random.default_rng(seed)
    con = _build_constellation(world, rng)
    traj = _trajectory(world)
    gt0 = traj(0.0)
    meas = _SandboxMeasurement(gt0, rng=rng, ideal=bool(world["ideal"]), terrain=bool(world["terrain"]))
    meas.iono_tow0 = float(world["iono_tow0"])

    winfo = SimpleNamespace(lat=world["lat"], lon=world["lon"], alt=world["alt"], gt0=gt0.copy(),
                            ideal=bool(world["ideal"]), systems=list(world["systems"]),
                            step_s=float(world["step_s"]), raim=dict(rcfg), seed=int(seed),
                            world=dict(world))
    attack = None
    if attack_spec:
        a = dict(attack_spec)
        attack = ATTACKS[a.pop("type")].factory(**a)
        if hasattr(attack, "bind"):
            attack.bind(SimpleNamespace(seed=int(seed), world=winfo))

    n_ep = int(round(world["duration_s"] / world["step_s"]))
    step = float(world["step_s"])
    rec = {name: {k: [] for k in _TRACE_KEYS} for name in est_names}

    with engine_settings(rcfg, world["max_sats"]):
        ests = [(name, ESTIMATORS[name].factory(winfo)) for name in est_names]
        last_pos = {name: None for name in est_names}
        driver_name, driver = ests[0]
        for k in range(n_ep):
            t = k * step
            con.update_all(t, ideal=bool(world["ideal"]))
            gt = traj(t)
            meas.set_position(gt)
            est = driver.estimate() if hasattr(driver, "estimate") else last_pos[driver_name]
            signals = meas.build(_visible_view(con, gt, world), t, est_pos=est,
                                 ref_pos=est if est is not None else gt)
            active = False
            if attack is not None:
                attack.apply(signals, t, gt, rng)
                active = bool(attack.is_active(t))
            faulty = set(attack.faulty_ids(t)) if (attack is not None and hasattr(attack, "faulty_ids")) else set()
            present = bool(faulty.intersection(s["sat_id"] for s in signals))
            target = attack.target_ecef(gt) if (attack is not None and active and hasattr(attack, "target_ecef")) else None
            R = enu_rotation(gt)
            for name, obj in ests:
                sig_copy = [dict(s) for s in signals]
                t0 = time.perf_counter()
                pos, info = obj.solve(sig_copy, t)
                dt_run = time.perf_counter() - t0
                info = info or {}
                r = rec[name]
                r["t"].append(t)
                r["runtime_s"].append(dt_run)
                r["n_sats"].append(len(signals))
                r["attack_active"].append(active)
                excl = list(info.get("excluded") or [])
                status = info.get("status")
                r["detect"].append(bool(info.get("alarm") or excl or status in ("alarm", "excluded")))
                r["excluded_n"].append(len(excl))
                r["faulty_excluded"].append(bool(faulty and faulty.intersection(excl)))
                r["fault_present"].append(present)
                ok = pos is not None and np.all(np.isfinite(pos))
                r["fix"].append(bool(ok))
                if ok:
                    last_pos[name] = np.array(pos, float)
                    d = R @ (np.asarray(pos, float) - gt)
                    r["err_h"].append(float(math.hypot(d[0], d[1])))
                    r["err_v"].append(float(abs(d[2])))
                    r["err_3d"].append(float(np.linalg.norm(d)))
                    r["hpl"].append(_f(info.get("hpl")))
                    r["vpl"].append(_f(info.get("vpl")))
                    nd = info.get("nis_dof")
                    r["nis_norm"].append(float(info["nis"]) / nd if nd else float("nan"))
                    r["gdop"].append(_f(info.get("gdop")))
                    r["target_dist"].append(float(np.linalg.norm(np.asarray(pos) - target))
                                            if target is not None else float("nan"))
                else:
                    for kk in ("err_h", "err_v", "err_3d", "hpl", "vpl", "nis_norm", "gdop", "target_dist"):
                        r[kk].append(float("nan"))

    has_faulty = attack is not None and hasattr(attack, "faulty_ids")
    traces = {}
    for name in est_names:
        tr = {k: np.array(v, dtype=bool if k in ("fix", "detect", "faulty_excluded", "fault_present", "attack_active") else float)
              for k, v in rec[name].items()}
        tr["meta"] = {"hal": float(rcfg["hal"]), "val": rcfg.get("val"),
                      "warmup_s": float(spec.warmup_s), "has_attack": attack is not None,
                      "attack_start": (float(getattr(attack, "start")) if attack is not None
                                       and getattr(attack, "start", None) is not None else None),
                      "has_faulty": has_faulty, "estimator": name, "seed": int(seed),
                      "location": location["name"]}
        traces[name] = tr
    return traces


def compute_metrics(trace, names):
    out = {}
    for m in names:
        try:
            v = METRICS[m].fn(trace)
            out[m] = float(v) if v is not None else float("nan")
        except Exception as e:  # noqa: BLE001 — pokvarena plugin metrika ne ruši eksperiment
            out[m] = float("nan")
            out.setdefault("_errors", {})[m] = repr(e)
    return out


# =============================================================================
# Jobovi i worker
# =============================================================================
def _make_jobs(spec):
    points = _sweep_points(spec)
    locs = _locations(spec.world)
    seeds = _seed_list(spec)
    pooled = bool(spec.world.get("pool_locations"))
    jobs = []
    for pi, p in enumerate(points):
        for li, loc in enumerate(locs):
            for s in seeds:
                group = pi if pooled else pi * len(locs) + li
                jobs.append({"idx": len(jobs), "point": pi, "group": group, "params": p,
                             "location": loc, "seed": s})
    return points, locs, jobs


def _run_job(payload):
    """Worker (top-level, picklabilan): jedan run → metrike po estimatoru."""
    spec_d, job = payload
    spec = parse_spec(spec_d)
    traces = simulate(spec, job["params"], job["location"], job["seed"])
    recs = []
    for est, tr in traces.items():
        recs.append({"estimator": est, "metrics": compute_metrics(tr, spec.metrics)})
    out = {"idx": job["idx"], "records": recs}
    if spec.save_traces:
        out["traces"] = {est: {k: v.tolist() for k, v in tr.items() if k != "meta"}
                         for est, tr in traces.items()}
    return out


def _worker_init(plugins, root):
    if root not in sys.path:
        sys.path.insert(0, root)
    load_plugins(plugins)


# =============================================================================
# Statistika
# =============================================================================
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
         9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
         16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074,
         23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045,
         30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t_crit_975(df):
    """Dvostrani 95 % kvantil Studentove t razdiobe (tablica + interpolacija u 1/df)."""
    if df <= 0:
        return float("nan")
    if df in _T975:
        return _T975[df]
    if df > 120:
        a, b, ta, tb = 120, math.inf, _T975[120], 1.960
        return tb + (ta - tb) * (a / df)
    keys = sorted(_T975)
    lo = max(k for k in keys if k < df)
    hi = min(k for k in keys if k > df)
    w = (1 / df - 1 / hi) / (1 / lo - 1 / hi)
    return _T975[hi] + w * (_T975[lo] - _T975[hi])


def summarize(values):
    """mean/median/p95/std/min/max i 95 % CI srednje vrijednosti (t-razdioba) preko sjemena."""
    a = np.asarray([v for v in values if v is not None], float)
    a = a[np.isfinite(a)]
    n = len(a)
    nan = float("nan")
    if n == 0:
        return {"n": 0, "mean": nan, "median": nan, "p95": nan, "std": nan, "min": nan,
                "max": nan, "ci_lo": nan, "ci_hi": nan}
    mean = float(a.mean())
    std = float(a.std(ddof=1)) if n > 1 else nan
    half = t_crit_975(n - 1) * std / math.sqrt(n) if n > 1 else nan
    return {"n": n, "mean": mean, "median": float(np.median(a)),
            "p95": float(np.percentile(a, 95)), "std": std, "min": float(a.min()),
            "max": float(a.max()), "ci_lo": mean - half if n > 1 else nan,
            "ci_hi": mean + half if n > 1 else nan}


# =============================================================================
# Rezultat
# =============================================================================
def _git_info():
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True, timeout=5)
        if rev.returncode != 0:
            return None
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                               capture_output=True, text=True, timeout=5)
        return {"commit": rev.stdout.strip(), "dirty": bool(dirty.stdout.strip())}
    except (OSError, subprocess.SubprocessError):
        return None


def jsonable(x):
    """numpy/NaN → čisti JSON (NaN/inf → None)."""
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return jsonable(x.tolist())
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        x = float(x)
        return x if math.isfinite(x) else None
    return x


def _label(v):
    if isinstance(v, list):
        return "+".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, sort_keys=True)
    return str(v)


@dataclass
class Result:
    """Rezultat eksperimenta (obični dict/list/numpy — zgodno za notebook)."""
    spec: dict
    points: list           # [{index, params}]
    locations: list
    runs: list             # [{idx, point, group, location, seed, estimator, params, metrics}]
    aggregate: list        # [{point, group, location, estimator, params, metrics: {m: summary}}]
    meta: dict
    traces: list = None    # [{idx, estimator, seed, location, params, trace}] ako save_traces

    # ---- pristup ----
    @property
    def metric_names(self):
        return list(self.spec.get("metrics") or [])

    @property
    def sweep_keys(self):
        return list((self.spec.get("sweep") or {}).keys())

    def table(self, metric, stat="mean", estimator=None):
        """numpy niz `stat` za metriku po redovima agregata (filtar estimatora)."""
        rows = [a for a in self.aggregate if estimator is None or a["estimator"] == estimator]
        return np.array([a["metrics"][metric][stat] for a in rows], float)

    def rows(self, estimator=None):
        return [a for a in self.aggregate if estimator is None or a["estimator"] == estimator]

    def deterministic_view(self):
        """Agregat bez nedeterminističkih metrika (za provjeru reproducibilnosti)."""
        keep = [m for m in self.metric_names if METRICS.get(m) is None or METRICS[m].deterministic]
        return [{"point": a["point"], "group": a["group"], "estimator": a["estimator"],
                 "metrics": {m: a["metrics"][m] for m in keep}} for a in self.aggregate]

    def to_dict(self, include_traces=False):
        d = {"spec": self.spec, "points": self.points, "locations": self.locations,
             "runs": self.runs, "aggregate": self.aggregate, "meta": self.meta}
        if include_traces and self.traces is not None:
            d["traces"] = self.traces
        return jsonable(d)

    # ---- izvoz ----
    def csv_text(self, kind="aggregate"):
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        keys = self.sweep_keys
        multi_loc = len(self.locations) > 1 and not (self.spec.get("world") or {}).get("pool_locations")
        if kind == "aggregate":
            stats = ("mean", "ci_lo", "ci_hi", "median", "p95", "std", "n")
            head = ["point"] + keys + (["location"] if multi_loc else []) + ["estimator"]
            for m in self.metric_names:
                head += [f"{m}_{s}" for s in stats]
            w.writerow(head)
            for a in self.aggregate:
                row = [a["point"]] + [_label(a["params"].get(k)) for k in keys]
                row += ([a["location"]] if multi_loc else []) + [a["estimator"]]
                for m in self.metric_names:
                    s = a["metrics"][m]
                    row += [_csvnum(s[x]) for x in stats]
                w.writerow(row)
        else:
            head = ["run", "point"] + keys + ["location", "seed", "estimator"] + self.metric_names
            w.writerow(head)
            for r in self.runs:
                row = [r["idx"], r["point"]] + [_label(r["params"].get(k)) for k in keys]
                row += [r["location"], r["seed"], r["estimator"]]
                row += [_csvnum(r["metrics"].get(m)) for m in self.metric_names]
                w.writerow(row)
        return buf.getvalue()

    def save(self, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        paths = {}
        p = os.path.join(out_dir, "results.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)
        paths["json"] = p
        for kind, fn in (("aggregate", "results.csv"), ("runs", "runs.csv")):
            p = os.path.join(out_dir, fn)
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(self.csv_text(kind))
            paths[kind] = p
        if self.traces:
            tdir = os.path.join(out_dir, "traces")
            os.makedirs(tdir, exist_ok=True)
            for tr in self.traces:
                fn = os.path.join(tdir, f"run{tr['idx']:04d}_{tr['estimator']}.csv")
                cols = [k for k in _TRACE_KEYS if k in tr["trace"]]
                with open(fn, "w", encoding="utf-8", newline="") as f:
                    w = csv.writer(f, lineterminator="\n")
                    w.writerow(cols)
                    for row in zip(*[tr["trace"][c] for c in cols]):
                        w.writerow([_csvnum(v) for v in row])
            paths["traces"] = tdir
        return paths

    def plot(self, metric=None, x=None, out=None, logx=None, title=None):
        return plot_result(self, metric=metric, x=x, out=out, logx=logx, title=title)


def _csvnum(v):
    if v is None:
        return ""
    if isinstance(v, (bool, np.bool_)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return "" if not math.isfinite(float(v)) else repr(float(v))
    return v


def _aggregate(spec, points, locs, jobs, outs):
    pooled = bool(spec.world.get("pool_locations"))
    runs = []
    by_group = {}
    for job in jobs:
        o = outs.get(job["idx"])
        if o is None:
            continue
        for rec in o["records"]:
            runs.append({"idx": job["idx"], "point": job["point"], "group": job["group"],
                         "location": job["location"]["name"], "seed": job["seed"],
                         "estimator": rec["estimator"], "params": job["params"],
                         "metrics": rec["metrics"]})
            by_group.setdefault((job["group"], rec["estimator"]), []).append(rec["metrics"])
    aggregate = []
    est_order = []
    for job in jobs:
        for e in (job["params"].get("estimator") and [job["params"]["estimator"]]) or spec.estimators:
            if e not in est_order:
                est_order.append(e)
    groups = sorted({j["group"] for j in jobs})
    for g in groups:
        job0 = next(j for j in jobs if j["group"] == g)
        for e in est_order:
            ms = by_group.get((g, e))
            if not ms:
                continue
            aggregate.append({"point": job0["point"], "group": g,
                              "location": "pooled" if pooled else job0["location"]["name"],
                              "estimator": e, "params": job0["params"],
                              "metrics": {m: summarize([r.get(m) for r in ms]) for m in spec.metrics}})
    return runs, aggregate


# =============================================================================
# Glavni API
# =============================================================================
def run(spec, workers=1, progress=None, cancel=None, verbose=False):
    """Odvrti eksperiment. Vrati Result.

    workers:  broj procesa (1 = u ovom procesu). Rezultat ne ovisi o broju workera.
    progress: callback(done, total) nakon svakog runa.
    cancel:   objekt s .is_set() (npr. threading.Event) — prekid između runova.
    Ctrl+C prekida; vraća se djelomičan Result s meta["interrupted"] = True.
    """
    spec_obj, errs = validate(spec if not isinstance(spec, Spec) else asdict(spec))
    if errs:
        raise SpecError(errs)
    spec_d = asdict(spec_obj)
    points, locs, jobs = _make_jobs(spec_obj)
    total = len(jobs)
    outs = {}
    t_start = time.time()
    interrupted = False
    cancelled = False

    def _tick(o):
        outs[o["idx"]] = o
        if progress:
            progress(len(outs), total)
        if verbose:
            j = jobs[o["idx"]]
            lab = ", ".join(f"{k}={_label(v)}" for k, v in j["params"].items()) or "-"
            el = time.time() - t_start
            eta = el / len(outs) * (total - len(outs))
            print(f"[{len(outs):4d}/{total}] {lab} | {j['location']['name']} seed={j['seed']}"
                  f"  ({el:6.1f} s, ETA {eta:6.1f} s)", file=sys.stderr, flush=True)

    payloads = [(spec_d, j) for j in jobs]
    workers = max(1, int(workers or 1))
    try:
        if workers == 1 or total <= 1:
            for p in payloads:
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    break
                _tick(_run_job(p))
        else:
            import multiprocessing as mp
            ctx = mp.get_context("spawn")
            pool = ctx.Pool(min(workers, total), initializer=_worker_init,
                            initargs=(list(spec_obj.plugins), ROOT))
            try:
                for o in pool.imap_unordered(_run_job, payloads, chunksize=1):
                    _tick(o)
                    if cancel is not None and cancel.is_set():
                        cancelled = True
                        break
                if cancelled:
                    pool.terminate()
                else:
                    pool.close()
            except BaseException:
                pool.terminate()
                raise
            finally:
                pool.join()
    except KeyboardInterrupt:
        interrupted = True
        if verbose:
            print("\n[prekinuto] spremam djelomične rezultate…", file=sys.stderr)

    runs, aggregate = _aggregate(spec_obj, points, locs, jobs, outs)
    traces = None
    if spec_obj.save_traces:
        traces = []
        for j in jobs:
            o = outs.get(j["idx"])
            if o is None:
                continue
            for est, tr in o.get("traces", {}).items():
                traces.append({"idx": j["idx"], "estimator": est, "seed": j["seed"],
                               "location": j["location"]["name"], "params": j["params"],
                               "trace": tr})
    meta = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "elapsed_s": time.time() - t_start,
            "workers": workers, "runs_done": len(outs), "runs_total": total,
            "interrupted": interrupted, "cancelled": cancelled, "git": _git_info(),
            "numpy": np.__version__, "python": sys.version.split()[0],
            "spec_version": SPEC_VERSION,
            "nondeterministic_metrics": [m for m in spec_obj.metrics if not METRICS[m].deterministic]}
    return Result(spec=jsonable(spec_d), points=[{"index": i, "params": p} for i, p in enumerate(points)],
                  locations=locs, runs=runs, aggregate=aggregate, meta=meta, traces=traces)


def load_spec(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_examples():
    """[(datoteka, spec dict)] iz sandbox/examples."""
    out = []
    if os.path.isdir(EXAMPLES_DIR):
        for fn in sorted(os.listdir(EXAMPLES_DIR)):
            if fn.endswith(".json"):
                out.append((fn, load_spec(os.path.join(EXAMPLES_DIR, fn))))
    return out


# =============================================================================
# Graf (matplotlib opcionalno)
# =============================================================================
def _is_num(v):
    return _num(v)


def plot_result(res, metric=None, x=None, out=None, logx=None, title=None):
    """Metrika vs sweep parametar, s 95 % CI vrpcom; jedna linija po ostalim parametrima × estimatoru."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metric = metric or res.metric_names[0]
    keys = [k for k in res.sweep_keys]
    multi_loc = len({a["location"] for a in res.aggregate}) > 1
    x = x or (keys[0] if keys else ("location" if multi_loc else None))

    def xval(a):
        return a["location"] if x == "location" else (a["params"].get(x) if x else 0)
    bg, fg, grid = "#0d1117", "#e6edf3", "#30363d"
    colors = ["#39c5cf", "#e3b341", "#58d364", "#f8776a", "#bc8cff", "#ff9bce", "#8b949e"]

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    for sp in ax.spines.values():
        sp.set_color(grid)
    ax.tick_params(colors=fg)
    ax.grid(True, color=grid, alpha=0.6, lw=0.5)

    groups = {}
    for a in res.aggregate:
        other = tuple((k, _label(a["params"].get(k))) for k in keys if k != x)
        loc = a["location"] if (multi_loc and x != "location") else None
        groups.setdefault((other, loc, a["estimator"]), []).append(a)
    xs_all = [xval(a) for a in res.aggregate]
    numeric = x is not None and all(_is_num(v) for v in xs_all)
    cats = []
    if not numeric:
        for v in xs_all:
            if _label(v) not in cats:
                cats.append(_label(v))
    n_est = len({a["estimator"] for a in res.aggregate})
    for gi, ((other, loc, est), rows) in enumerate(groups.items()):
        c = colors[gi % len(colors)]
        xv = [xval(a) for a in rows]
        xp = np.array(xv, float) if numeric else np.array([cats.index(_label(v)) for v in xv], float)
        order = np.argsort(xp)
        xp = xp[order]
        mean = np.array([rows[i]["metrics"][metric]["mean"] for i in order], float)
        lo = np.array([rows[i]["metrics"][metric]["ci_lo"] for i in order], float)
        hi = np.array([rows[i]["metrics"][metric]["ci_hi"] for i in order], float)
        parts = [f"{k.split('.')[-1]}={v}" for k, v in other]
        if loc:
            parts.append(loc)
        if n_est > 1 or not parts:
            parts.append(est)
        lab = ", ".join(parts)
        if numeric:
            ax.plot(xp, mean, color=c, lw=1.8, marker="o", ms=4, label=lab)
            okb = np.isfinite(lo) & np.isfinite(hi)
            if okb.any():
                ax.fill_between(xp[okb], lo[okb], hi[okb], color=c, alpha=0.18, lw=0)
        else:
            off = (gi - (len(groups) - 1) / 2) * 0.08
            yerr = np.vstack([mean - lo, hi - mean])
            yerr = np.where(np.isfinite(yerr), yerr, 0.0)
            ax.errorbar(xp + off, mean, yerr=yerr, color=c, lw=1.6, marker="o", ms=5,
                        capsize=4, label=lab)
    if not numeric:
        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels(cats, color=fg)
    if logx or (logx is None and numeric and x and x.endswith(("pfa", "pmd"))):
        ax.set_xscale("log")
    unit = METRICS[metric].unit if metric in METRICS else ""
    ax.set_xlabel(x or "", color=fg)
    ax.set_ylabel(metric + (f" [{unit}]" if unit else ""), color=fg)
    n_seeds = max((a["metrics"][metric]["n"] for a in res.aggregate), default=0)
    ax.set_title(title or f"{res.spec.get('name', '')} — {metric} (srednja vrijednost, 95 % CI, n≤{n_seeds})",
                 color=fg, fontsize=10)
    if groups:
        ax.legend(facecolor=bg, edgecolor=grid, labelcolor=fg, fontsize=8)
    fig.tight_layout()
    out = out or f"plot_{metric}.png"
    fig.savefig(out, dpi=110, facecolor=bg)
    plt.close(fig)
    return out


# =============================================================================
# CLI
# =============================================================================
def _plot_specs(spec_d, res):
    p = spec_d.get("plot")
    if not p:
        return [{"metric": res.metric_names[0]}]
    return p if isinstance(p, list) else [p]


def cmd_run(args):
    spec_d = load_spec(args.spec)
    spec_obj, errs = validate(spec_d)
    if errs:
        print("Spec nije ispravan:", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 2
    sz = plan_size(spec_obj)
    print(f"[sandbox] {spec_obj.name}: {sz['points']} točaka × {sz['locations']} lok. × "
          f"{sz['seeds']} sjemena = {sz['runs']} runova ({sz['epochs']} epoha·estimatora), "
          f"workers={args.workers}", file=sys.stderr)
    res = run(spec_d, workers=args.workers, verbose=True)
    out = args.out or os.path.join("results", spec_obj.name)
    paths = res.save(out)
    print(f"[sandbox] {res.meta['runs_done']}/{res.meta['runs_total']} runova u "
          f"{res.meta['elapsed_s']:.1f} s{' (PREKINUTO)' if res.meta['interrupted'] else ''}")
    for k, p in paths.items():
        print(f"  {k:9s} {p}")
    if args.plot:
        try:
            for ps in _plot_specs(spec_d, res):
                p = res.plot(metric=ps.get("metric"), x=ps.get("x"), logx=ps.get("logx"),
                             title=ps.get("title"),
                             out=os.path.join(out, f"plot_{ps.get('metric') or res.metric_names[0]}.png"))
                print(f"  plot      {p}")
        except ImportError:
            print("  (matplotlib nije instaliran — preskačem graf)")
    _print_summary(res)
    return 130 if res.meta["interrupted"] else 0


def _print_summary(res, max_metrics=6):
    ms = res.metric_names[:max_metrics]
    keys = res.sweep_keys
    head = " | ".join([*(k.split(".")[-1] for k in keys), "est", *ms])
    print(head)
    print("-" * len(head))
    for a in res.aggregate:
        cells = [_label(a["params"].get(k)) for k in keys] + [a["estimator"]]
        for m in ms:
            s = a["metrics"][m]
            cells.append("—" if s["n"] == 0 else (f"{s['mean']:.3g}±{(s['ci_hi'] - s['mean']):.2g}"
                                                 if math.isfinite(s["ci_hi"]) else f"{s['mean']:.3g}"))
        print(" | ".join(cells))


def cmd_validate(args):
    spec_d = load_spec(args.spec)
    spec_obj, errs = validate(spec_d)
    if errs:
        print("NEISPRAVAN:")
        for e in errs:
            print("  - " + e)
        return 2
    sz = plan_size(spec_obj)
    print(f"OK: {spec_obj.name} — {sz['points']} točaka, {sz['runs']} runova, {sz['epochs']} epoha·estimatora")
    return 0


def cmd_list(args):
    load_plugins(args.plugin or [])
    for title, reg in (("Estimatori", ESTIMATORS), ("Napadi", ATTACKS), ("Metrike", METRICS)):
        print(f"{title}:")
        for name in sorted(reg):
            e = reg[name]
            nd = "  [nedeterministička]" if getattr(e, "deterministic", True) is False else ""
            print(f"  {name:24s} {e.description}{nd}")
        print()
    ex = list_examples()
    if ex:
        print("Primjeri (sandbox/examples):")
        for fn, d in ex:
            print(f"  {fn:28s} {d.get('description', '')[:90]}")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):          # hrvatski znakovi na Windows konzoli
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Istraživački sandbox: sweep × Monte Carlo × algoritmi.")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run", help="odvrti eksperiment iz JSON speca")
    pr.add_argument("spec")
    pr.add_argument("--workers", type=int, default=1)
    pr.add_argument("--out", default=None, help="izlazni direktorij (zadano results/<ime>)")
    pr.add_argument("--plot", action="store_true", help="spremi PNG metrike vs sweep parametar")
    pr.set_defaults(func=cmd_run)
    pv = sub.add_parser("validate", help="provjeri spec")
    pv.add_argument("spec")
    pv.set_defaults(func=cmd_validate)
    pl = sub.add_parser("list", help="popiši registrirane estimatore/napade/metrike")
    pl.add_argument("--plugin", action="append", help="dodatni plugin modul/.py")
    pl.set_defaults(func=cmd_list)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    # Pokreni kroz modul `sandbox` (ne `__main__`) da worker procesi i plugini dijele
    # iste registre (spawn na Windowsima re-importa glavni modul pod drugim imenom).
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import sandbox as _self
    sys.exit(_self.main())
