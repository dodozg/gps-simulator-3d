"""Poglavlje 6 — najmanji kvadrati: Gauss-Newton iz središta Zemlje, težinski vs. obični LS.

Ispisuje brojke koje se citiraju u tekstu i rješenjima (zato se skripta vrti pri svakoj
promjeni modela: knjiga i simulator ostaju usklađeni).
"""
import csv
import json
import os

import numpy as np

from stil import PLAVA, NARANCASTA, SIVA, UDZBENIK, plt, spremi, decimalni_zarez

from physics_engine import calculate_sagnac_correction
from realdata import to_enu
from receiver import Receiver, meas_sigma
from satellite import WalkerDeltaConstellation
from utils import lla_to_ecef

LAT, LON, ALT = 45.815, 15.982, 120.0      # Zagreb
SJEME = 6
PODACI = os.path.join(UDZBENIK, "podaci")
os.makedirs(PODACI, exist_ok=True)


def gauss_newton(signals, x0=None, iteracije=8, tezine=None):
    """Isti model kao hladni start prijemnika: ρ = |s − x| + c·b + Sagnac."""
    x = np.zeros(4) if x0 is None else np.array(x0, float)
    povijest = [x.copy()]
    for _ in range(iteracije):
        G, y = [], []
        for s in signals:
            d = x[:3] - s["broadcast_pos"]
            r = max(np.linalg.norm(d), 1.0)
            y.append(s["pseudorange"] - (r + x[3] + calculate_sagnac_correction(s["broadcast_pos"], x[:3])))
            G.append([*(d / r), 1.0])
        G, y = np.array(G), np.array(y)
        if tezine is not None:
            w = np.sqrt(tezine)
            G, y = G * w[:, None], y * w
        dx = np.linalg.lstsq(G, y, rcond=None)[0]
        x = x + dx
        povijest.append(x.copy())
    return x, povijest


def sin_el(s, pos):
    up = pos / np.linalg.norm(pos)
    los = s["broadcast_pos"] - pos
    return float(np.dot(up, los / np.linalg.norm(los)))


def main():
    rng = np.random.default_rng(SJEME)
    con = WalkerDeltaConstellation(rng=rng)
    for sat in con.satellites:
        sat.is_spoofed = False      # ugrađeni RAIM-demo kvar (6 km nakon 200 s) — vidi pogl. 10
    gt = np.array(lla_to_ecef(LAT, LON, ALT))
    rx = Receiver(gt, rng=rng)
    brojke = {}

    # ---------------------------------------------------------- 1) jedna epoha, Gauss-Newton
    con.update_all(0.0)
    sig = rx.receive_signals(con, 0.0)
    x, pov = gauss_newton(sig)
    gr = [float(np.linalg.norm(p[:3] - gt)) for p in pov]
    brojke["gn_n_sat"] = len(sig)
    brojke["gn_greske_m"] = [round(g, 3) for g in gr]
    brojke["gn_cb_m"] = round(float(x[3]), 1)

    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    ax.semilogy(range(len(gr)), gr, "o-", color=PLAVA)
    for k, g in enumerate(gr[:6]):
        ax.annotate(f"{g:,.0f} m".replace(",", " ") if g > 10 else f"{g:.2f} m".replace(".", ","),
                    (k, g), textcoords="offset points", xytext=(6, 4), fontsize=7.5, color=SIVA)
    ax.set_xlabel("iteracija Gauss-Newtona")
    ax.set_ylabel("|x̂ − x| [m]")
    ax.set_title(f"Hladni start iz središta Zemlje (Zagreb, {len(sig)} satelita)")
    ax.set_ylim(min(gr) / 3, max(gr) * 4)
    spremi(fig, "06-gauss-newton")

    # podaci za računsku vježbu: jedna epoha (prvih 6 satelita)
    with open(os.path.join(PODACI, "epoha_zagreb.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sat", "x_m", "y_m", "z_m", "pseudoudaljenost_m", "sigma_m"])
        for s in sig[:6]:
            w.writerow([s["sat_id"], *(f"{v:.3f}" for v in s["broadcast_pos"]),
                        f"{s['pseudorange']:.3f}", f"{meas_sigma(s, sin_el(s, gt)):.2f}"])
    x6, _ = gauss_newton(sig[:6])
    e6 = to_enu(x6[:3] - gt, gt)
    brojke["vjezba_6sat_enu_m"] = [round(float(v), 2) for v in e6]
    brojke["vjezba_6sat_cb_m"] = round(float(x6[3]), 2)
    x4, _ = gauss_newton(sig[:4])
    brojke["vjezba_4sat_greska_m"] = round(float(np.linalg.norm(x4[:3] - gt)), 2)
    G4 = []
    for s in sig[:4]:
        d = x4[:3] - s["broadcast_pos"]
        G4.append([*(d / np.linalg.norm(d)), 1.0])
    brojke["vjezba_4sat_rezidual_max_m"] = float(np.max(np.abs(
        [s["pseudorange"] - (np.linalg.norm(x4[:3] - s["broadcast_pos"]) + x4[3]
                             + calculate_sagnac_correction(s["broadcast_pos"], x4[:3])) for s in sig[:4]])))

    # ---------------------------------------------------------- 2) 600 epoha: LS vs WLS
    obicni, tezinski = [], []
    xa = xb = np.r_[gt + 100.0, 0.0]
    satovi = []
    for t in range(1, 601):
        con.update_all(float(t))
        sig = rx.receive_signals(con, float(t))
        rx.solve_position()                      # EKF vodi selekciju satelita, kao u aplikaciji
        if len(sig) < 5:
            continue
        # pravi prijemnik kreće od prethodnog rješenja (sat prijemnika "bježi" ~300 m/s)
        w = np.array([1.0 / meas_sigma(s, sin_el(s, gt)) ** 2 for s in sig])
        a, _ = gauss_newton(sig, xa, 6)
        b, _ = gauss_newton(sig, xb, 6, tezine=w)
        xa, xb = a, b
        satovi.append((t, float(a[3])))
        obicni.append(to_enu(a[:3] - gt, gt))
        tezinski.append(to_enu(b[:3] - gt, gt))
    obicni, tezinski = np.array(obicni), np.array(tezinski)
    ts, cbs = np.array(satovi).T
    brojke["drift_sata_m_po_s"] = round(float(np.polyfit(ts, cbs, 1)[0]), 1)

    def stat(e):
        h = np.hypot(e[:, 0], e[:, 1])
        return dict(h50=round(float(np.median(h)), 2), h95=round(float(np.percentile(h, 95)), 2),
                    v95=round(float(np.percentile(np.abs(e[:, 2]), 95)), 2),
                    sred_e=round(float(e[:, 0].mean()), 2), sred_n=round(float(e[:, 1].mean()), 2),
                    sred_u=round(float(e[:, 2].mean()), 2))
    brojke["ls"] = stat(obicni)
    brojke["wls"] = stat(tezinski)
    brojke["n_epoha"] = len(obicni)

    fig, axs = plt.subplots(1, 2, figsize=(6.4, 3.3), sharex=True, sharey=True)
    lim = float(np.percentile(np.abs(np.r_[obicni[:, :2], tezinski[:, :2]]), 99.5)) * 1.1
    for ax, e, naslov, boja, k in ((axs[0], obicni, "obični LS", NARANCASTA, "ls"),
                                   (axs[1], tezinski, "težinski LS (σ iz C/N0 i elevacije)", PLAVA, "wls")):
        ax.scatter(e[:, 0], e[:, 1], s=4, alpha=0.45, color=boja, linewidths=0)
        r95 = brojke[k]["h95"]
        ax.add_patch(plt.Circle((0, 0), r95, fill=False, ls="--", lw=1, color="black"))
        ax.text(0.03, 0.04, f"p95 = {r95:.1f} m".replace(".", ","), transform=ax.transAxes, fontsize=8)
        ax.set_title(naslov)
        ax.set_aspect("equal")
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_xlabel("istok [m]")
        decimalni_zarez(ax)
    axs[0].set_ylabel("sjever [m]")
    spremi(fig, "06-ls-vs-wls")

    with open(os.path.join(UDZBENIK, "skripte", "brojke_06.json"), "w", encoding="utf-8") as f:
        json.dump(brojke, f, indent=1, ensure_ascii=False)
    print(json.dumps(brojke, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
