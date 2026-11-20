"""Pozicioniranje na PRAVIM GNSS podacima: RINEX opažanja + broadcast efemeride.

Jednofrekvencijski (GPS L1 C/A) "single point positioning" (SPP). Svaka epoha
RINEX opažanja pretvara se u ISTI oblik mjerenja koji koristi simulator
(`received_signals`: sat_id, system, sat_pos, broadcast_pos, pseudorange,
true_dist) i predaje POSTOJEĆEM estimatoru `receiver.Receiver` — dakle isti EKF,
RAIM i NIS dijagnostika rade i na stvarnim podacima.

Korekcije pseudoudaljenosti C1 (prije predaje estimatoru):
  + c·Δt_sv          sat satelita (af0/af1/af2 + relativistički član)  [ephemeris.py]
  − c·TGD            grupno kašnjenje za L1 C/A korisnika
  − I_Klobuchar      ionosfera, koeficijenti α/β iz zaglavlja nav datoteke
                     (`physics_engine.klobuchar_delay`)
  − T_Saastamoinen   troposfera (standardna atmosfera, vidi `tropo_saastamoinen`)

Pozicija satelita računa se u trenutku ODAŠILJANJA (t_rx − PR/c − Δt_sv) u ECEF
okviru tog trenutka, BEZ rotacije Zemlje tijekom leta signala: `Receiver`
sam dodaje Sagnac član (`physics_engine.calculate_sagnac_correction`) i u LS
inicijalizaciji i u EKF modelu, pa bi dodatna rotacija ovdje bila dvostruko
uračunata (~10–30 m pomaka). Test `test_earth_rotation_not_double_counted`
to provjerava na rezultatu.

Referentna pozicija za grešku: APPROX POSITION XYZ iz zaglavlja RINEX-a (+ DELTA
H/E/N antene) ili zadana `--ref`. Pazi: APPROX POSITION je u nekim datotekama samo
grubi položaj; za uzorak (GEONET 0759) je to koordinata stanice.

Pokretanje:
    python realdata.py tests/data/07590920.05o tests/data/07590920.05n
    python realdata.py obs.rnx nav.rnx --plot realdata.png --mask 10
    python realdata.py obs.rnx nav.rnx --solver ls --ref -3976219.5 3382372.6 3652513.0
"""
from __future__ import annotations

import argparse
import os

import numpy as np

import rinex
from ephemeris import (C_LIGHT, sat_clock, sat_position, select_ephemeris)
from physics_engine import calculate_sagnac_correction, klobuchar_delay
from receiver import Receiver, SIGMA_ZENITH, MIN_SIN_ELEV
from utils import ecef_to_lla

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "data")
SAMPLE_OBS = os.path.join(DATA_DIR, "07590920.05o")
SAMPLE_NAV = os.path.join(DATA_DIR, "07590920.05n")

DEFAULT_MASK_DEG = 10.0
# Skok sata prijemnika: neki prijemnici sat drže unutar ±1 ms skokovima (300 km
# u pseudoudaljenosti, zajednički svim satelitima). EKF to ne može pratiti kroz
# procesni šum, pa se c·bias ponovno postavi iz medijane inovacija ako je
# zajednički pomak veći od ovog praga.
CLOCK_JUMP_M = 200.0


# --- geometrija ---------------------------------------------------------------
def enu_basis(pos):
    """Jedinični vektori (east, north, up) u geodetskoj točki `pos` (ECEF)."""
    lat, lon, _ = ecef_to_lla(*pos)
    la, lo = np.radians(lat), np.radians(lon)
    sl, cl, so, co = np.sin(la), np.cos(la), np.sin(lo), np.cos(lo)
    return (np.array([-so, co, 0.0]),
            np.array([-sl * co, -sl * so, cl]),
            np.array([cl * co, cl * so, sl]))


def az_el(rec, sat):
    """(azimut, elevacija) [rad] satelita gledano iz prijemnika (ECEF)."""
    e, n, u = enu_basis(rec)
    d = np.asarray(sat) - np.asarray(rec)
    d = d / np.linalg.norm(d)
    return float(np.arctan2(d @ e, d @ n)), float(np.arcsin(np.clip(d @ u, -1.0, 1.0)))


def to_enu(delta, ref):
    e, n, u = enu_basis(ref)
    return np.array([delta @ e, delta @ n, delta @ u])


# --- atmosfera ----------------------------------------------------------------
def tropo_saastamoinen(lat_rad, h_m, elev_rad, humidity=0.7):
    """Troposfersko kašnjenje [m]: Saastamoinen + standardna atmosfera.

    Tlak/temperatura/vlaga iz standardne atmosfere na visini h (kao u RTKLIB
    `tropmodel`), mapiranje 1/cos(z). Zenitno ~2.3–2.5 m na razini mora.
    """
    if elev_rad <= 0.0 or h_m < -100.0 or h_m > 1e4:
        return 0.0
    hgt = max(h_m, 0.0)
    pres = 1013.25 * (1.0 - 2.2557e-5 * hgt) ** 5.2568            # [hPa]
    temp = 15.0 - 6.5e-3 * hgt + 273.16                           # [K]
    e = 6.108 * humidity * np.exp((17.15 * temp - 4684.0) / (temp - 38.45))  # [hPa]
    z = np.pi / 2.0 - elev_rad
    dry = 0.0022768 * pres / (1.0 - 0.00266 * np.cos(2.0 * lat_rad) - 0.00028 * hgt / 1e3) / np.cos(z)
    wet = 0.002277 * (1255.0 / temp + 0.05) * e / np.cos(z)
    return float(dry + wet)


# --- mjerenja -----------------------------------------------------------------
def build_measurements(obs, epoch, nav, ref_pos=None, mask_deg=DEFAULT_MASK_DEG,
                       iono=True, tropo=True, truth=None):
    """Jedna RINEX epoha -> lista mjerenja u formatu `Receiver.received_signals`.

    ref_pos: približna pozicija prijemnika (prethodno rješenje) za elevacijsku
    masku i atmosferske korekcije; None -> bez maske i bez atmosfere (hladni start).
    truth: referentna pozicija, SAMO za analitičko polje `true_dist`.
    Dodatna polja (elev_deg, az_deg, iono_m, tropo_m, sat_clock_m) su dijagnostika.
    """
    alpha = nav.header.iono_alpha
    beta = nav.header.iono_beta
    use_iono = iono and alpha is not None and beta is not None and ref_pos is not None
    if ref_pos is not None:
        lat, lon, h = ecef_to_lla(*ref_pos)
    _, tow = rinex.gps_week_tow(epoch.t)
    out = []
    for sat, rec in sorted(obs.gps_l1(epoch).items()):
        pr = rec["C1"]
        ephs = nav.ephemerides.get(sat)
        if not ephs:
            continue
        t_tx = epoch.t - pr / C_LIGHT                    # vrijeme odašiljanja (sat satelita)
        eph = select_ephemeris(ephs, t_tx)
        if eph is None:
            continue
        dts = sat_clock(eph, t_tx)                        # uklj. relativistički član
        t_tx -= dts                                       # -> GPS vrijeme odašiljanja
        dts = sat_clock(eph, t_tx)
        pos, _ = sat_position(eph, t_tx)                  # ECEF(t_tx), BEZ Sagnac rotacije
        corr = pr + C_LIGHT * (dts - eph.tgd)
        m = {"sat_id": sat, "system": "GPS", "sat_pos": pos, "broadcast_pos": pos,
             "sat_clock_m": C_LIGHT * dts, "iono_m": 0.0, "tropo_m": 0.0}
        if ref_pos is not None:
            az, el = az_el(ref_pos, pos)
            if el < np.radians(mask_deg):
                continue
            m["elev_deg"], m["az_deg"] = float(np.degrees(el)), float(np.degrees(az) % 360.0)
            if use_iono:
                m["iono_m"] = C_LIGHT * klobuchar_delay(lat, lon, el, az, tow, alpha, beta)
            if tropo:
                m["tropo_m"] = tropo_saastamoinen(np.radians(lat), h, el)
        m["pseudorange"] = corr - m["iono_m"] - m["tropo_m"]
        m["true_dist"] = float(np.linalg.norm(pos - truth)) if truth is not None else float("nan")
        if "S1" in rec:
            m["snr_dbhz"] = rec["S1"]
        out.append(m)
    return out


# --- težinski LS (snapshot, za usporedbu s EKF-om i hladni start) -------------
def solve_ls(meas, x0=None, max_iter=15):
    """Težinski Gauss-Newton za [x, y, z, c·bias], ISTI model kao `Receiver`
    (geometrija + c·bias + Sagnac), težine 1/σ², σ = SIGMA_ZENITH/sin(el).

    Vraća dict(pos, clock_m, gdop, residuals) ili None (premalo satelita/divergencija).
    """
    if len(meas) < 4:
        return None
    x = np.zeros(4) if x0 is None else np.array([*x0[:3], 0.0 if len(x0) < 4 else x0[3]], float)
    for _ in range(max_iter):
        H, r, w = [], [], []
        up = x[:3] / max(np.linalg.norm(x[:3]), 1.0)
        for m in meas:
            s = m["broadcast_pos"]
            d = x[:3] - s
            rho = max(np.linalg.norm(d), 1.0)
            pred = rho + x[3] + calculate_sagnac_correction(s, x[:3])
            H.append([*(d / rho), 1.0])
            r.append(m["pseudorange"] - pred)
            if np.linalg.norm(x[:3]) > 6e6:
                sin_el = max(float(up @ (-d / rho)), MIN_SIN_ELEV)
            else:
                sin_el = 1.0                               # još nema smislene elevacije
            w.append((sin_el / SIGMA_ZENITH) ** 2)
        H, r, W = np.array(H), np.array(r), np.diag(w)
        try:
            N = H.T @ W @ H
            dx = np.linalg.solve(N, H.T @ W @ r)
        except np.linalg.LinAlgError:
            return None
        x += dx
        if np.linalg.norm(dx[:3]) < 1e-4:
            break
    else:
        if np.linalg.norm(dx[:3]) > 1.0:
            return None
    try:
        gdop = float(np.sqrt(np.trace(np.linalg.inv(H.T @ H))))
    except np.linalg.LinAlgError:
        gdop = float("nan")
    return {"pos": x[:3].copy(), "clock_m": float(x[3]), "gdop": gdop, "residuals": r}


def _reseed_clock_on_jump(rx, meas, t):
    """Ako je zajednički pomak inovacija > CLOCK_JUMP_M (skok sata prijemnika),
    ponovno postavi c·bias u EKF-u (vrati iznos skoka [m] ili 0)."""
    if not rx.ekf_initialized:
        return 0.0
    dt = t - rx.ekf_last_time
    p = rx.x_ekf[:3] + rx.x_ekf[3:6] * dt
    b = rx.x_ekf[6] + rx.x_ekf[7] * dt
    inn = [m["pseudorange"] - (np.linalg.norm(p - m["broadcast_pos"]) + b
                               + calculate_sagnac_correction(m["broadcast_pos"], p)) for m in meas]
    off = float(np.median(inn))
    if abs(off) > CLOCK_JUMP_M:
        rx.x_ekf[6] += off
        rx.P_ekf[6, :] = 0.0
        rx.P_ekf[:, 6] = 0.0
        rx.P_ekf[6, 6] = 1e4
        return off
    return 0.0


def reference_position(obs, ref=None):
    """Referentna pozicija ANTENE: zadana `ref` ili APPROX POSITION + DELTA H/E/N."""
    if ref is not None:
        return np.asarray(ref, float)
    p = obs.header.approx_pos
    if p is None:
        return None
    dh, de, dn = obs.header.antenna_delta_hen
    e, n, u = enu_basis(p)
    return p + dh * u + de * e + dn * n


# --- glavna obrada --------------------------------------------------------------
def process(obs, nav, ref=None, mask_deg=DEFAULT_MASK_DEG, solver="ekf",
            iono=True, tropo=True, max_epochs=None, raim=True):
    """SPP kroz sve epohe. Vraća dict s nizovima po epohi i sažetkom.

    solver='ekf' -> `receiver.Receiver` (EKF + RAIM + NIS); 'ls' -> snapshot
    težinski LS (`solve_ls`). LS rješenje se računa uvijek (stupac `ls_*`) radi
    usporedbe.
    """
    if isinstance(obs, str):
        obs = rinex.read_obs(obs)
    if isinstance(nav, str):
        nav = rinex.read_nav(nav)
    truth = reference_position(obs, ref)
    epochs = obs.epochs[:max_epochs] if max_epochs else obs.epochs
    if not epochs:
        raise ValueError("RINEX opažanja nemaju epoha")
    t0 = epochs[0].t

    rx = Receiver(pos=truth if truth is not None else np.zeros(3), ideal=True)
    rx.raim_enabled = raim
    est = None
    rows = []
    for ep in epochs:
        t_rel = ep.t - t0
        if est is None:                                    # hladni start: LS bez atmosfere/maske
            boot = solve_ls(build_measurements(obs, ep, nav, None, iono=False, tropo=False))
            if boot is None:
                rows.append(_row(t_rel, ep, None, None, [], truth, None, ""))
                continue
            est = boot["pos"]
        meas = build_measurements(obs, ep, nav, est, mask_deg, iono, tropo, truth)
        ls = solve_ls(meas, x0=est)
        pos, gdop, alarm, nis = None, None, "", None
        if solver == "ekf":
            rx.meas.received_signals = meas
            rx.meas.last_update_time = t_rel
            _reseed_clock_on_jump(rx, meas, t_rel)
            pos, gdop = rx.solve_position()
            alarm = rx.raim_alarm
            nis = (rx.nis / rx.nis_dof) if rx.nis_dof else None
            if pos is not None and not np.all(np.isfinite(pos)):
                pos = None
        elif ls is not None:
            pos, gdop = ls["pos"], ls["gdop"]
        if pos is not None:
            est = np.array(pos, float)
        rows.append(_row(t_rel, ep, pos, gdop, meas, truth, ls, alarm, nis))
    return _assemble(rows, obs, truth, solver, mask_deg)


def _row(t_rel, ep, pos, gdop, meas, truth, ls, alarm, nis=None):
    r = {"t": t_rel, "gps_t": ep.t, "nsat": len(meas), "gdop": gdop, "alarm": alarm,
         "nis": nis, "pos": None if pos is None else np.array(pos, float),
         "enu": None, "ls_enu": None,
         "sats": [m["sat_id"] for m in meas]}
    if truth is not None:
        if pos is not None:
            r["enu"] = to_enu(np.asarray(pos) - truth, truth)
        if ls is not None:
            r["ls_enu"] = to_enu(ls["pos"] - truth, truth)
    return r


def summarize(enus):
    """Sažetak grešaka iz liste ENU vektora (None se preskače)."""
    E = np.array([e for e in enus if e is not None])
    if len(E) == 0:
        return {"n": 0}
    hz = np.hypot(E[:, 0], E[:, 1])
    v = np.abs(E[:, 2])
    return {
        "n": int(len(E)),
        "h_median": float(np.median(hz)), "h_p95": float(np.percentile(hz, 95)),
        "v_median": float(np.median(v)), "v_p95": float(np.percentile(v, 95)),
        "d3_rms": float(np.sqrt(np.mean(np.sum(E ** 2, axis=1)))),
        "mean_enu": [float(x) for x in E.mean(axis=0)],
        "h_max": float(hz.max()), "v_max": float(v.max()),
    }


def _assemble(rows, obs, truth, solver, mask_deg):
    alarms = [(r["t"], r["alarm"]) for r in rows if r["alarm"]]
    return {
        "station": obs.header.marker_name,
        "receiver": obs.header.receiver_type,
        "start_gps_t": rows[0]["gps_t"] if rows else None,
        "start_utc_like": str(rinex.gps_to_datetime(rows[0]["gps_t"])) if rows else None,
        "reference": truth,
        "solver": solver,
        "mask_deg": mask_deg,
        "rows": rows,
        "summary": summarize([r["enu"] for r in rows]),
        "ls_summary": summarize([r["ls_enu"] for r in rows]),
        "raim_alarms": alarms,
        "n_epochs": len(rows),
        "solved": sum(1 for r in rows if r["pos"] is not None),
    }


def to_api(res):
    """Rezultat -> kompaktni JSON-friendly oblik (za /api/realdata)."""
    rows = res["rows"]

    def col(key, idx=None, fn=None):
        out = []
        for r in rows:
            v = r[key]
            if v is None:
                out.append(None)
            elif fn is not None:
                out.append(float(fn(v)))
            elif idx is not None:
                out.append(float(v[idx]))
            else:
                out.append(v)
        return out

    hz = lambda e: np.hypot(e[0], e[1])  # noqa: E731
    return {
        "ok": res["solved"] > 0,
        "station": res["station"], "receiver": res["receiver"],
        "start": res["start_utc_like"], "solver": res["solver"], "mask_deg": res["mask_deg"],
        "reference": None if res["reference"] is None else [float(x) for x in res["reference"]],
        "t": [r["t"] for r in rows],
        "h_err": col("enu", fn=hz), "v_err": col("enu", idx=2),
        "e_err": col("enu", idx=0), "n_err": col("enu", idx=1),
        "ls_h_err": col("ls_enu", fn=hz), "ls_v_err": col("ls_enu", idx=2),
        "nsat": [r["nsat"] for r in rows], "gdop": col("gdop"), "nis": col("nis"),
        "raim_alarms": res["raim_alarms"],
        "summary": res["summary"], "ls_summary": res["ls_summary"],
        "n_epochs": res["n_epochs"], "solved": res["solved"],
    }


_SAMPLE_CACHE = {}


def run_sample(mask_deg=DEFAULT_MASK_DEG, solver="ekf"):
    """Obradi priloženi uzorak (tests/data, GEONET 0759, 2005-04-02) — za web API."""
    key = (round(float(mask_deg), 3), solver)
    if key not in _SAMPLE_CACHE:
        obs = rinex.read_obs(SAMPLE_OBS)
        nav = rinex.read_nav(SAMPLE_NAV)
        res = to_api(process(obs, nav, mask_deg=mask_deg, solver=solver))
        res["source"] = "RTKLIB test data (BSD-2), GSI GEONET 0759, 07590920.05o/.05n"
        _SAMPLE_CACHE[key] = res
    return _SAMPLE_CACHE[key]


# --- CLI ----------------------------------------------------------------------
def _fmt(x, w=7, p=2):
    return f"{x:{w}.{p}f}" if x is not None and np.isfinite(x) else " " * (w - 1) + "—"


def print_report(res, per_epoch=True):
    print(f"Stanica: {res['station'] or '?'}  prijemnik: {res['receiver'] or '?'}  "
          f"početak: {res['start_utc_like']} GPST  solver: {res['solver']}  maska: {res['mask_deg']}°")
    if res["reference"] is not None:
        print("Referenca (ECEF): " + "  ".join(f"{v:.3f}" for v in res["reference"]))
    if per_epoch:
        print(f"{'t[s]':>7} {'sat':>3} {'E[m]':>7} {'N[m]':>7} {'U[m]':>7} {'H[m]':>7} {'GDOP':>6}  RAIM")
        for r in res["rows"]:
            e = r["enu"]
            if e is None:
                print(f"{r['t']:7.1f} {r['nsat']:3d}   (nema rješenja)")
                continue
            print(f"{r['t']:7.1f} {r['nsat']:3d} {_fmt(e[0])} {_fmt(e[1])} {_fmt(e[2])} "
                  f"{_fmt(np.hypot(e[0], e[1]))} {_fmt(r['gdop'], 6)}  {r['alarm']}")
    for name, s in (("EKF (Receiver)" if res["solver"] == "ekf" else "LS", res["summary"]),
                    ("LS snapshot", res["ls_summary"])):
        if s.get("n", 0) == 0:
            print(f"{name}: nema rješenja")
            continue
        print(f"{name}: epoha {s['n']}/{res['n_epochs']} | horizontalno medijan {s['h_median']:.2f} m, "
              f"95% {s['h_p95']:.2f} m | vertikalno medijan {s['v_median']:.2f} m, 95% {s['v_p95']:.2f} m "
              f"| 3D RMS {s['d3_rms']:.2f} m | srednji ENU "
              + "/".join(f"{v:+.2f}" for v in s["mean_enu"]) + " m")
    if res["raim_alarms"]:
        print(f"RAIM alarmi: {len(res['raim_alarms'])}")


def plot(res, out_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib nije instaliran (pip install -r requirements-plots.txt) — preskačem graf.")
        return None
    rows = [r for r in res["rows"] if r["enu"] is not None]
    if not rows:
        print("Nema rješenja za crtanje.")
        return None
    t = np.array([r["t"] for r in rows]) / 60.0
    E = np.array([r["enu"] for r in rows])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5), gridspec_kw={"width_ratios": [2, 1]})
    a1.plot(t, E[:, 0], label="E"); a1.plot(t, E[:, 1], label="N"); a1.plot(t, E[:, 2], label="U")
    a1.axhline(0, color="k", lw=0.5)
    a1.set_xlabel("min od početka"); a1.set_ylabel("greška [m]"); a1.legend(); a1.grid(alpha=0.3)
    a1.set_title(f"SPP greška — {res['station']} ({res['solver']})")
    a2.scatter(E[:, 0], E[:, 1], s=8)
    a2.set_aspect("equal"); a2.grid(alpha=0.3); a2.set_xlabel("E [m]"); a2.set_ylabel("N [m]")
    a2.set_title("horizontalno")
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"Graf spremljen: {out_path}")
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="SPP na pravim RINEX podacima (GPS L1 C/A).")
    ap.add_argument("obs", help="RINEX datoteka opažanja (v2.1x/v3.0x)")
    ap.add_argument("nav", help="RINEX GPS navigacijska datoteka (v2/v3)")
    ap.add_argument("--ref", nargs=3, type=float, metavar=("X", "Y", "Z"),
                    help="referentna ECEF pozicija [m] (zadano: APPROX POSITION iz zaglavlja)")
    ap.add_argument("--mask", type=float, default=DEFAULT_MASK_DEG, help="elevacijska maska [°]")
    ap.add_argument("--solver", choices=("ekf", "ls"), default="ekf")
    ap.add_argument("--no-iono", action="store_true", help="bez Klobuchar korekcije")
    ap.add_argument("--no-tropo", action="store_true", help="bez troposferske korekcije")
    ap.add_argument("--no-raim", action="store_true")
    ap.add_argument("--max-epochs", type=int, default=None)
    ap.add_argument("--quiet", action="store_true", help="samo sažetak")
    ap.add_argument("--plot", nargs="?", const="realdata.png", default=None, metavar="PNG",
                    help="spremi PNG graf (zahtijeva matplotlib)")
    a = ap.parse_args(argv)
    res = process(a.obs, a.nav, ref=a.ref, mask_deg=a.mask, solver=a.solver,
                  iono=not a.no_iono, tropo=not a.no_tropo, max_epochs=a.max_epochs,
                  raim=not a.no_raim)
    print_report(res, per_epoch=not a.quiet)
    if a.plot:
        plot(res, a.plot)
    return res


if __name__ == "__main__":
    main()
