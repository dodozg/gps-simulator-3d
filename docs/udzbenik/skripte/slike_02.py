"""Poglavlje 2 — koordinate i vrijeme: Sagnacova korekcija i što se dogodi kad je model izostavi."""
import csv
import json
import os

import numpy as np

from stil import NARANCASTA, PLAVA, SUSTAVI, UDZBENIK, decimalni_zarez, plt, spremi

from physics_engine import C, MU, calculate_sagnac_correction, get_relativistic_drift_rate
from realdata import az_el, to_enu
from receiver import Receiver
from satellite import WalkerDeltaConstellation
from utils import ecef_to_lla, lla_to_ecef

LAT, LON, ALT = 45.815, 15.982, 120.0
SJEME = 6


def ls(signals, x0, sagnac=True, iteracije=6):
    x = np.array(x0, float)
    for _ in range(iteracije):
        G, y = [], []
        for s in signals:
            d = x[:3] - s["broadcast_pos"]
            r = np.linalg.norm(d)
            sg = calculate_sagnac_correction(s["broadcast_pos"], x[:3]) if sagnac else 0.0
            y.append(s["pseudorange"] - (r + x[3] + sg))
            G.append([*(d / r), 1.0])
        x = x + np.linalg.lstsq(np.array(G), np.array(y), rcond=None)[0]
    return x


def main():
    rx = np.array(lla_to_ecef(LAT, LON, ALT))
    brojke = {"zagreb_ecef_m": [round(float(v), 3) for v in rx]}
    from utils import WGS84_A, WGS84_E2
    brojke["zagreb_N_m"] = round(float(WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(np.radians(LAT)) ** 2)), 1)
    brojke["zagreb_r_km"] = round(float(np.linalg.norm(rx)) / 1e3, 1)
    brojke["v_rot_mps"] = round(float(7.2921159e-5 * np.hypot(rx[0], rx[1])), 0)
    brojke["pomak_75ms_m"] = round(float(7.2921159e-5 * np.hypot(rx[0], rx[1]) * 0.075), 1)
    brojke["zagreb_lla_natrag"] = [round(float(v), 9) for v in ecef_to_lla(*rx)]

    # ------------------------------------------------ 1) Sagnac po azimutu kroz 12 h
    con = WalkerDeltaConstellation(rng=np.random.default_rng(0))
    az, sg, el = [], [], []
    for t in np.arange(0.0, 43200.0, 300.0):
        con.update_all(t)
        for s in con.satellites:
            a, e = az_el(rx, s.current_pos)
            if np.degrees(e) >= 5.0:
                az.append(np.degrees(a) % 360.0)
                el.append(np.degrees(e))
                sg.append(calculate_sagnac_correction(s.current_pos, rx))
    az, sg, el = map(np.array, (az, sg, el))
    brojke["sagnac_min_m"] = round(float(sg.min()), 1)
    brojke["sagnac_max_m"] = round(float(sg.max()), 1)
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    sc = ax.scatter(az, sg, c=el, s=6, cmap="viridis", vmin=5, vmax=90, linewidths=0)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xlabel("azimut satelita [°]  (0 = sjever, 90 = istok)")
    ax.set_ylabel("Sagnacova korekcija [m]")
    ax.set_xticks(range(0, 361, 45))
    ax.set_xlim(0, 360)
    cb = fig.colorbar(sc, ax=ax, pad=0.01)
    cb.set_label("elevacija [°]")
    decimalni_zarez(ax)
    spremi(fig, "02-sagnac-azimut")

    # ------------------------------------------------ 2) LS sa i bez Sagnaca u modelu
    rng = np.random.default_rng(SJEME)
    con = WalkerDeltaConstellation(rng=rng)
    for s in con.satellites:
        s.is_spoofed = False
    rcv = Receiver(rx, rng=rng)
    xa = xb = np.r_[rx + 100.0, 0.0]
    sa, sb = [], []
    for t in range(0, 600):
        con.update_all(float(t))
        sig = rcv.receive_signals(con, float(t))
        rcv.solve_position()
        if len(sig) < 5:
            continue
        xa = ls(sig, xa, True)
        xb = ls(sig, xb, False)
        sa.append(to_enu(xa[:3] - rx, rx))
        sb.append(to_enu(xb[:3] - rx, rx))
    sa, sb = np.array(sa), np.array(sb)
    brojke["s_sagnacom_sred_enu_m"] = [round(float(v), 2) for v in sa.mean(axis=0)]
    brojke["bez_sagnaca_sred_enu_m"] = [round(float(v), 2) for v in sb.mean(axis=0)]
    brojke["bez_sagnaca_pomak_h_m"] = round(float(np.hypot(*sb.mean(axis=0)[:2])), 1)
    fig, ax = plt.subplots(figsize=(4.6, 3.6))
    ax.scatter(sa[:, 0], sa[:, 1], s=4, alpha=0.5, color=PLAVA, linewidths=0, label="model sa Sagnacom")
    ax.scatter(sb[:, 0], sb[:, 1], s=4, alpha=0.5, color=NARANCASTA, linewidths=0, label="model bez Sagnaca")
    for e, boja in ((sa, PLAVA), (sb, NARANCASTA)):
        m = e.mean(axis=0)
        ax.plot(m[0], m[1], "+", color="black", ms=10, mew=1.5)
    ax.axhline(0, color="black", lw=0.5)
    ax.axvline(0, color="black", lw=0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("istok [m]")
    ax.set_ylabel("sjever [m]")
    ax.legend(loc="upper left", markerscale=3)
    decimalni_zarez(ax)
    spremi(fig, "02-bez-sagnaca")

    # ------------------------------------------------ 3) relativnost i podaci za vježbu
    a_gps = con.satellites[0].a
    e_gps = con.satellites[0].e
    brojke["rel_drift_s_po_s"] = get_relativistic_drift_rate(a_gps)
    brojke["rel_us_po_danu"] = round(get_relativistic_drift_rate(a_gps) * 86400 * 1e6, 1)
    brojke["rel_km_po_danu"] = round(get_relativistic_drift_rate(a_gps) * 86400 * C / 1e3, 1)
    amp = 2.0 * np.sqrt(MU * a_gps) / C ** 2 * e_gps
    brojke["ekscentricitet_walker"] = e_gps
    brojke["rel_ekscentr_amp_ns"] = round(float(amp * 1e9), 1)
    brojke["rel_ekscentr_amp_m"] = round(float(amp * C), 1)
    with open(os.path.join(UDZBENIK, "podaci", "epoha_zagreb.csv"), encoding="utf-8") as f:
        prvi = next(csv.DictReader(f))
    sp = np.array([float(prvi[k]) for k in ("x_m", "y_m", "z_m")])
    a, e = az_el(rx, sp)
    brojke["vjezba_sat"] = prvi["sat"]
    brojke["vjezba_az_deg"] = round(float(np.degrees(a) % 360), 2)
    brojke["vjezba_el_deg"] = round(float(np.degrees(e)), 2)
    brojke["vjezba_enu_km"] = [round(float(v) / 1e3, 1) for v in to_enu(sp - rx, rx)]
    # geocentrična vs geodetska širina u Zagrebu
    brojke["geocentricna_sirina_deg"] = round(float(np.degrees(np.arctan2(rx[2], np.hypot(rx[0], rx[1])))), 4)

    with open(os.path.join(UDZBENIK, "skripte", "brojke_02.json"), "w", encoding="utf-8") as f:
        json.dump(brojke, f, indent=1, ensure_ascii=False)
    print(json.dumps(brojke, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
