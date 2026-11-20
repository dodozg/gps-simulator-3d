"""Poglavlje 8 — Kalmanov filtar: konvergencija i 2σ, utjecaj procesnog šuma Q, EKF vs WLS (sandbox)."""
import json
import os

import numpy as np

from stil import NARANCASTA, PLAVA, SIVA, UDZBENIK, ZELENA, CRVENA, agregat, decimalni_zarez, plt, spremi, ucitaj_studiju

import receiver as rmod
from realdata import enu_basis, to_enu
from receiver import Receiver
from satellite import WalkerDeltaConstellation
from utils import lla_to_ecef

LAT, LON, ALT = 45.815, 15.982, 120.0


def nova(seed):
    rng = np.random.default_rng(seed)
    con = WalkerDeltaConstellation(rng=rng)
    for s in con.satellites:
        s.is_spoofed = False
    gt = np.array(lla_to_ecef(LAT, LON, ALT))
    return con, Receiver(gt, rng=rng), gt


def konvergencija(b):
    con, rx, gt = nova(8)
    e, n, u = enu_basis(gt)
    Rm = np.vstack([e, n, u])
    T = 300
    err, sig, nis = [], [], []
    for t in range(T):
        con.update_all(float(t))
        rx.receive_signals(con, float(t))
        p, _ = rx.solve_position()
        if p is None:
            err.append([np.nan] * 3)
            sig.append([np.nan] * 3)
            nis.append(np.nan)
            continue
        err.append(Rm @ (p - gt))
        P = Rm @ rx.P_ekf[:3, :3] @ Rm.T
        sig.append(np.sqrt(np.diag(P)))
        nis.append(rx.nis / rx.nis_dof if rx.nis_dof else np.nan)
    err, sig, nis = np.array(err), np.array(sig), np.array(nis)
    t = np.arange(T)
    fig, axs = plt.subplots(3, 1, figsize=(6.4, 4.6), sharex=True)
    for k, (ax, ime) in enumerate(zip(axs, ("istok", "sjever", "gore"))):
        ax.fill_between(t, -2 * sig[:, k], 2 * sig[:, k], color=PLAVA, alpha=0.15, linewidth=0, label="±2σ iz P")
        ax.plot(t, err[:, k], color=PLAVA, lw=1)
        ax.axhline(0, color="black", lw=0.5)
        ax.set_ylabel(f"{ime} [m]")
        ax.set_ylim(-25, 25)
        decimalni_zarez(ax)
    axs[0].legend(loc="upper right")
    axs[-1].set_xlabel("vrijeme od hladnog starta [s]")
    spremi(fig, "08-konvergencija")
    m = t >= 30
    unutar = np.mean(np.abs(err[m]) <= 2 * sig[m], axis=0)
    b.update(konv_unutar_2sigma=[round(float(x) * 100, 1) for x in unutar],
             konv_sigma_kraj=[round(float(x), 2) for x in sig[-1]],
             konv_sigma_1s=[round(float(x), 1) for x in sig[1]],
             konv_nis_sred=round(float(np.nanmean(nis[30:])), 2),
             konv_greska_med=round(float(np.nanmedian(np.linalg.norm(err[30:], axis=1))), 2))


def q_studija(b):
    """Skaliraj procesni šum Q (pozicija i brzina) za statičan i pokretan prijemnik."""
    faktori = [0.01, 0.1, 1.0, 10.0, 100.0]
    izvorno = (rmod.Q_POS, rmod.Q_VEL)
    rezultat = {"staticki": [], "let": []}
    try:
        for f in faktori:
            rmod.Q_POS, rmod.Q_VEL = izvorno[0] * f, izvorno[1] * f
            for scen in rezultat:
                gr = []
                for seed in (21, 22):
                    con, rx, gt0 = nova(seed)
                    e, n, u = enu_basis(gt0)
                    for t in range(400):
                        if scen == "let":       # krug polumjera 2 km brzinom 60 m/s (a ≈ 1,8 m/s²)
                            w = 60.0 / 2000.0
                            gt = gt0 + 2000.0 * (np.cos(w * t) - 1) * e + 2000.0 * np.sin(w * t) * n
                            rx.set_position(gt)
                        else:
                            gt = gt0
                        con.update_all(float(t))
                        rx.receive_signals(con, float(t))
                        p, _ = rx.solve_position()
                        if p is not None and t >= 60:
                            gr.append(float(np.linalg.norm(p - gt)))
                gr = np.array(gr)
                rezultat[scen].append(dict(f=f, med=round(float(np.median(gr)), 2), p95=round(float(np.percentile(gr, 95)), 2)))
    finally:
        rmod.Q_POS, rmod.Q_VEL = izvorno
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    for scen, boja, opis in (("staticki", PLAVA, "statičan prijemnik"), ("let", NARANCASTA, "let po krugu, 60 m/s")):
        r = rezultat[scen]
        ax.plot([x["f"] for x in r], [x["p95"] for x in r], "o-", color=boja, label=f"{opis}, p95")
        ax.plot([x["f"] for x in r], [x["med"] for x in r], "o--", color=boja, lw=1, ms=3, label=f"{opis}, medijan")
    ax.axvline(1.0, color=SIVA, lw=0.8, ls=":")
    ax.text(1.08, ax.get_ylim()[1] * 0.92, "simulator", fontsize=7.5, color=SIVA)
    ax.set_xscale("log")
    ax.set_xlabel("faktor procesnog šuma (Q_POS, Q_VEL × faktor)")
    ax.set_ylabel("3D pogreška [m]")
    ax.set_ylim(0, None)
    ax.legend(fontsize=7)
    spremi(fig, "08-q")
    b["q_studija"] = rezultat


def ekf_wls(b):
    r = ucitaj_studiju("ekf_vs_wls")
    if r is None:
        return
    # uparena usporedba: ista lokacija i sjeme, EKF vs WLS
    po = {}
    for run in r["runs"]:
        po.setdefault((run["location"], run["seed"]), {})[run["estimator"]] = run["metrics"]
    parovi = [(v["ekf"]["h_err_p95"], v["wls"]["h_err_p95"]) for v in po.values() if "ekf" in v and "wls" in v]
    b["ekfwls_parova"] = len(parovi)
    b["ekfwls_ekf_bolji"] = int(sum(1 for a, c in parovi if a < c))
    tab = {}
    for st in agregat(r, ("h_err_p95", "v_err_p95", "nis_mean", "runtime_ms")):
        tab.setdefault(st["location"], {})[st["estimator"]] = {k: round(st[k]["mean"], 2) for k in ("h_err_p95", "v_err_p95", "nis_mean", "runtime_ms")}
    b["ekfwls_tablica"] = tab


def main():
    b = {"Q": dict(pos=rmod.Q_POS, vel=rmod.Q_VEL, bias=rmod.Q_BIAS, drift=rmod.Q_DRIFT, isb=rmod.Q_ISB)}
    konvergencija(b)
    q_studija(b)
    ekf_wls(b)
    with open(os.path.join(UDZBENIK, "skripte", "brojke_08.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps(b, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
