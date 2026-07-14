"""numpy -> JSON serijalizacija stanja simulacije za frontend.

Jedan `state_frame(session)` dict opisuje sve što web sučelje treba nacrtati u
jednoj epohi: prijemnik (procjena + istina), sateliti (pozicije, el/az, praćen/
odbačen, rezidual) i integritet (RAIM, NIS). Sve numpy vrijednosti -> obični
float/list radi JSON-a.
"""
import math

import numpy as np

from utils import ecef_to_lla, format_dms
from skyplot import enu_azel


def _num(x):
    """Konačan broj -> float; nan/inf -> None (JSON ne podnosi ne-konačne)."""
    x = float(x)
    return x if math.isfinite(x) else None


def to_jsonable(obj):
    """Rekurzivno pretvori numpy/tuple/set u JSON-safe strukture (nan/inf -> None)."""
    if isinstance(obj, np.ndarray):
        return [to_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (np.floating, float)):
        return _num(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    return obj


def _ecef(vec):
    """ECEF vektor -> lista float/None (nekonačne komponente -> None, kao _num).

    Ako EKF divergira, `calc_pos` može kolabirati (npr. blizu ishodišta) ili
    postati nekonačan; ne smije proći kao sirovi broj jer frontend (Cesium) ne
    može projicirati takvu točku i sruši render loop.
    """
    return [_num(v) for v in vec]


def _lla(ecef):
    lat, lon, alt = ecef_to_lla(ecef[0], ecef[1], ecef[2])
    return {"lat": _num(lat), "lon": _num(lon), "alt": _num(alt)}


def _dms(lla):
    lat, lon = lla["lat"], lla["lon"]
    return {"lat": format_dms(lat, True) if lat is not None else None,
            "lon": format_dms(lon, False) if lon is not None else None}


def state_frame(session):
    rx = session.receiver
    placed = session.gt_pos is not None
    initialized = bool(rx.ekf_initialized)

    # --- prijemnik ---
    receiver = {"placed": placed, "ekf_initialized": initialized}
    if placed:
        gt_lla = _lla(session.gt_pos)
        receiver["truth"] = {"lla": gt_lla, "dms": _dms(gt_lla),
                             "ecef": _ecef(session.gt_pos)}
    if initialized and session.calc_pos is not None:
        est = np.asarray(session.calc_pos)
        est_lla = _lla(est)
        receiver["estimate"] = {"lla": est_lla, "dms": _dms(est_lla),
                                "ecef": _ecef(est)}
        receiver["error_m"] = _num(np.linalg.norm(est - session.gt_pos)) if placed else None
        receiver["velocity_ms"] = _num(np.linalg.norm(rx.x_ekf[3:6]))
    receiver["gdop"] = _num(session.gdop) if session.gdop is not None else None
    receiver["nis"] = _num(rx.nis) if rx.nis_dof else None
    receiver["nis_dof"] = int(rx.nis_dof)
    receiver["nis_ratio"] = _num(rx.nis / rx.nis_dof) if rx.nis_dof else None
    receiver["clock_bias_us"] = _num(rx.clock_bias * 1e6)

    # --- sateliti ---
    diag = rx.last_solution or {}
    sats = []
    for sat in session.constellation.satellites:
        pos = sat.current_pos
        entry = {"id": sat.sat_id, "system": sat.system,
                 "ecef": _ecef(pos), "lla": _lla(pos),
                 "tracked": sat.sat_id in session.tracked_ids}
        if placed:
            azel = enu_azel(session.gt_pos, pos)
            if azel is not None:
                entry["el"] = float(azel[0])
                entry["az"] = float(azel[1])
        d = diag.get(sat.sat_id)
        if d is not None:
            entry["rejected"] = bool(d["rejected"])
            entry["residual_m"] = float(d["residual_m"])
        sats.append(entry)

    return {
        "sim_time": float(session.sim_time),
        "playing": bool(session.playing),
        "time_scale": float(session.time_scale),
        "kinematic": bool(session.kinematic),
        "raim_enabled": bool(rx.raim_enabled),
        "iono_tow0": float(rx.iono_tow0),
        "attack": to_jsonable(session.attack) if session.attack else None,
        "attack_active": session.attack_active(),
        "attack_overlay": session.attack_overlay(),
        "raim_alarm": rx.raim_alarm or None,
        "sats_total": len(session.constellation.satellites),
        "sats_tracked": len(session.tracked_ids),
        "receiver": receiver,
        "satellites": sats,
    }
