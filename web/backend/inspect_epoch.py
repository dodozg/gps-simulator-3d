"""Pogled iznutra — sve međuveličine JEDNE epohe navigacijskog rješenja.

Iz snimke koju `Receiver.solve_position` sprema u `receiver.last_epoch` (+ istine
koju zna samo simulator) gradi JSON za edukativni modul u sučelju:

1. **Mjerenja**: po satelitu pseudoudaljenost, model (geometrija + sat + Sagnac +
   ISB), inovacija, σ, i "proračun greške" — od čega se sastoji razlika između
   izmjerene pseudoudaljenosti i prave geometrijske udaljenosti (to zna SAMO
   simulator; pravi prijemnik ne).
2. **Geometrija**: matrica geometrije G u ENU obliku i DOP-ovi iz (GᵀG)⁻¹.
3. **Kalmanov korak**: stanje prije predikcije → predikcija → ažuriranje (ENU,
   relativno prema istini), nesigurnosti iz P, doprinos svakog satelita korekciji.
4. **RAIM**: testna statistika vs prag na krivulji χ², normalizirani reziduali,
   nagibi (slopes) i HPL.

Ne mijenja stanje simulacije; poziva se pod istim lockom kao korak simulacije.
"""
import math

import numpy as np

import raim
from physics_engine import (C, calculate_sagnac_correction, calculate_tropospheric_delay)
from receiver import ISB_INDEX, SIGMA_ZENITH, RAIM_SIGMA_SCALE
from satellite import GNSS_SYSTEMS
from utils import ecef_to_lla


def _f(x):
    """float ili None (JSON ne podnosi NaN/inf)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _r(x, nd=3):
    v = _f(x)
    return None if v is None else round(v, nd)


def _enu_rot(pos):
    return raim._enu_rotation(pos)


def _azel(R, origin, target):
    v = R @ (np.asarray(target) - np.asarray(origin))
    n = np.linalg.norm(v)
    if n == 0:
        return None, None
    el = math.degrees(math.asin(max(-1.0, min(1.0, v[2] / n))))
    az = math.degrees(math.atan2(v[0], v[1])) % 360.0
    return az, el


def _chi2_pdf(x, k):
    if x <= 0:
        return 0.0
    a = 0.5 * k
    return math.exp((a - 1) * math.log(x) - 0.5 * x - a * math.log(2.0) - math.lgamma(a))


def _dops(G_enu):
    """DOP-ovi iz geometrije u ENU obliku (stupci: E, N, U, sat[, ISB...])."""
    try:
        Q = np.linalg.inv(G_enu.T @ G_enu)
    except np.linalg.LinAlgError:
        return None, None
    d = np.diag(Q)
    out = {
        "EDOP": math.sqrt(d[0]), "NDOP": math.sqrt(d[1]), "VDOP": math.sqrt(d[2]),
        "HDOP": math.sqrt(d[0] + d[1]), "PDOP": math.sqrt(d[0] + d[1] + d[2]),
        "TDOP": math.sqrt(d[3]), "GDOP": math.sqrt(float(np.trace(Q))),
    }
    return {k: _r(v) for k, v in out.items()}, Q


def build_inspect(session):
    rx = session.receiver
    E = getattr(rx, "last_epoch", None)
    if session.gt_pos is None:
        return {"available": False, "reason": "no_receiver"}
    if not E or not rx.ekf_initialized:
        return {"available": False, "reason": "no_solution"}

    truth = np.asarray(session.gt_pos, float)
    Rt = _enu_rot(truth)                     # ENU u istini (za greške)
    x_pred, x_upd, x_before = E["x_pred"], E["x_upd"], E["x_before"]
    Rp = _enu_rot(x_pred[:3])                # ENU u točki linearizacije (za geometriju)
    signals = E["signals"]
    used = E["used"]
    used_pos = {i: k for k, i in enumerate(used)}
    rejected = set(E["rejected"])
    excluded_ids = set((rx.integrity or {}).get("excluded", []))
    K, Y, H = E["K"], E["Y"], E["H"]
    sats_by_id = {s.sat_id: s for s in session.constellation.satellites}
    rx_clock_m = float(rx.clock_bias) * C

    # --- 1. mjerenja + proračun greške -------------------------------------
    meas = []
    for i, sig in enumerate(signals):
        sp_b = np.asarray(sig["broadcast_pos"], float)
        sp_t = np.asarray(sig["sat_pos"], float)
        diff = x_pred[:3] - sp_b
        r_model = max(float(np.linalg.norm(diff)), 1.0)
        sagnac_model = calculate_sagnac_correction(sp_b, x_pred[:3])
        isb_idx = ISB_INDEX.get(sig.get("system"))
        isb_model = float(x_pred[isb_idx]) if isb_idx is not None else 0.0
        az, el = _azel(Rp, x_pred[:3], sp_b)
        # σ koju je prijemnik STVARNO koristio (iz C/N0 signalnog modela ako postoji,
        # inače elevacijski model); RAIM σ je ista uz RAIM_SIGMA_SCALE.
        if i < len(E.get("raim_sigmas", [])):
            sigma = E["raim_sigmas"][i] / max(RAIM_SIGMA_SCALE, 1e-9)
        else:
            sigma = SIGMA_ZENITH / max(math.sin(math.radians(el or 0.0)), 0.1)

        true_range = float(np.linalg.norm(sp_t - truth))
        pr = float(sig["pseudorange"])
        # Proračun greške mjerenja (pr − prava udaljenost) — zna samo simulator.
        sat = sats_by_id.get(sig["sat_id"])
        fault = float(getattr(sat, "user_clock_offset_m", 0.0) or 0.0)
        if sat is not None and getattr(sat, "is_spoofed", False) and session.sim_time > 200.0:
            fault += 6000.0
        parts = {
            "rx_clock": rx_clock_m,
            "sagnac": float(calculate_sagnac_correction(sp_t, truth)),
            "isb": float(GNSS_SYSTEMS.get(sig.get("system"), {}).get("isb_m", 0.0)),
            "sat_fault": fault,
            # tropo: stvarno kašnjenje − korekcija koju je prijemnik primijenio (iz procjene)
            "tropo_resid": float(calculate_tropospheric_delay(sp_t, truth)
                                 - calculate_tropospheric_delay(sp_b, x_pred[:3])),
        }
        total = pr - true_range
        parts["remainder"] = total - sum(parts.values())   # multipath + šum (×iono-free) + napad
        # Greška MODELA (ne mjerenja): prijemnik računa udaljenost do OBJAVLJENE pozicije.
        eph_los = float(np.linalg.norm(sp_b - truth) - true_range)

        k = used_pos.get(i)
        entry = {
            "id": sig["sat_id"], "system": sig.get("system", "GPS"),
            "az": _r(az, 1), "el": _r(el, 1),
            "used": k is not None,
            "excluded": (i in rejected) or (sig["sat_id"] in excluded_ids),
            "pseudorange": _r(pr), "true_range": _r(true_range),
            "model": {"geometric": _r(r_model), "clock": _r(x_pred[6]),
                      "sagnac": _r(sagnac_model), "isb": _r(isb_model),
                      "predicted": _r(r_model + x_pred[6] + sagnac_model + isb_model)},
            "innovation": _r(E["innovations"][i]),
            "sigma": _r(sigma),
            "cn0_dbhz": _r(sig.get("cn0_dbhz"), 1),
            "error_budget": {kk: _r(v) for kk, v in parts.items()},
            "error_total": _r(total),
            "ephemeris_los": _r(eph_los),
            "los_enu": [_r(v, 5) for v in (Rp @ (-diff / r_model))],
        }
        if k is not None:
            dx = K[:, k] * Y[k]
            entry["gain_enu"] = [_r(v, 4) for v in (Rp @ K[0:3, k])]   # m korekcije po m inovacije
            entry["contribution_enu"] = [_r(v) for v in (Rp @ dx[0:3])]
        meas.append(entry)

    # --- 2. geometrija -------------------------------------------------------
    # ENU geometrija iskorištenih satelita: [-e, -n, -u (od satelita prema prijemniku)...]
    systems = sorted({signals[i].get("system", "GPS") for i in used})
    G_enu, G_ecef, sig_used = [], [], []
    for i in used:
        sig = signals[i]
        diff = x_pred[:3] - np.asarray(sig["broadcast_pos"], float)
        u = diff / max(np.linalg.norm(diff), 1.0)
        row_enu = list(Rp @ u) + [1.0 if sig.get("system", "GPS") == s else 0.0 for s in systems]
        G_enu.append(row_enu)
        G_ecef.append(list(u) + row_enu[3:])
        sig_used.append(meas[i]["sigma"] * 1.0)
    G_enu = np.array(G_enu)
    dops, Q = _dops(G_enu) if len(used) >= 3 + len(systems) else (None, None)
    geometry = {
        "columns": ["E", "N", "U"] + [f"sat {s}" for s in systems],
        "rows": [{"id": signals[i]["sat_id"], "g": [_r(v, 4) for v in G_enu[k]]}
                 for k, i in enumerate(used)],
        "dop": dops,
        "Q": [[_r(v, 4) for v in row] for row in Q] if Q is not None else None,
        "n": len(used), "m": 3 + len(systems),
    }

    # --- 3. Kalmanov korak (ENU relativno prema istini) ----------------------
    def enu_err(x):
        return [_r(v) for v in (Rt @ (np.asarray(x[:3]) - truth))]

    def enu_std(P):
        Pp = Rt @ P[0:3, 0:3] @ Rt.T
        return [_r(math.sqrt(max(v, 0.0))) for v in np.diag(Pp)]

    corr = x_upd[:3] - x_pred[:3]
    kalman = {
        "dt": _r(E["dt"]), "t": _r(E["t"], 1),
        "before": {"enu": enu_err(x_before), "clock_m": _r(x_before[6])},
        "predicted": {"enu": enu_err(x_pred), "clock_m": _r(x_pred[6]),
                      "std_enu": enu_std(E["P_pred"]),
                      "clock_std": _r(math.sqrt(max(E["P_pred"][6, 6], 0.0)))},
        "updated": {"enu": enu_err(x_upd), "clock_m": _r(x_upd[6]),
                    "std_enu": enu_std(E["P_upd"]),
                    "clock_std": _r(math.sqrt(max(E["P_upd"][6, 6], 0.0)))},
        "correction_enu": [_r(v) for v in (Rt @ corr)],
        "clock_correction_m": _r(x_upd[6] - x_pred[6]),
        "velocity_enu": [_r(v) for v in (Rt @ x_upd[3:6])],
        "nis": _r(rx.nis), "nis_dof": int(rx.nis_dof),
        "true_clock_m": _r(rx_clock_m),
    }

    # --- 4. RAIM -------------------------------------------------------------
    integ = dict(rx.integrity or {})
    raim_view = {"integrity": {k: (v if k in ("pfa", "pmd") else
                                   _r(v) if isinstance(v, (float, np.floating)) else v)
                               for k, v in integ.items()}}
    if len(used) > geometry["m"]:
        y = np.array([E["innovations"][i] for i in used])
        sig_r = np.array([E["raim_sigmas"][i] for i in used])
        G_r = np.array(G_ecef)
        sol = raim._solve(G_r, y, sig_r)
        if sol is not None:
            Kr, Sr, r, T = sol
            dof = len(used) - G_r.shape[1]
            sii = np.clip(np.diag(Sr), 1e-12, None)
            wnorm = np.abs(r) / (sig_r * np.sqrt(sii))
            Kenu = Rp @ Kr[0:3, :]
            ok = np.diag(Sr) > 1e-9
            hslope = np.where(ok, np.hypot(Kenu[0], Kenu[1]) * sig_r / np.sqrt(sii), 0.0)
            vslope = np.where(ok, np.abs(Kenu[2]) * sig_r / np.sqrt(sii), 0.0)
            td = raim.chi2_isf(raim.RAIM_PFA, dof)
            lam = raim.noncentrality(dof)
            xmax = max(td * 1.25, T * 1.1, 2.0 * dof + 6)
            xs = np.linspace(0.0, xmax, 121)
            raim_view.update({
                "test": _r(T), "threshold": _r(td), "dof": dof,
                "lambda": _r(lam), "pbias": _r(math.sqrt(lam)),
                "pfa": raim.RAIM_PFA, "pmd": raim.RAIM_PMD,
                "pdf_x": [_r(v, 3) for v in xs], "pdf_y": [_r(_chi2_pdf(v, dof), 6) for v in xs],
                "sats": [{"id": signals[i]["sat_id"], "residual": _r(r[k]),
                          "normalized": _r(wnorm[k]), "sigma": _r(sig_r[k]),
                          "hslope": _r(hslope[k]), "vslope": _r(vslope[k])}
                         for k, i in enumerate(used)],
            })

    est_lla = ecef_to_lla(*x_upd[:3])
    return {
        "available": True,
        "sim_time": _r(session.sim_time, 1),
        "estimate_lla": [_r(v, 6) for v in est_lla],
        "error_m": _r(np.linalg.norm(x_upd[:3] - truth)),
        "measurements": meas,
        "geometry": geometry,
        "kalman": kalman,
        "raim": raim_view,
    }
