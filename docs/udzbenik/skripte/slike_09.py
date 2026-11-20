"""Poglavlje 9 — multi-GNSS: konvergencija ISB-a u EKF-u i studija sustavi × maska."""
import json
import os

import numpy as np

from stil import SUSTAVI, UDZBENIK, agregat, decimalni_zarez, plt, spremi, ucitaj_studiju

from receiver import ISB_INDEX, Receiver
from satellite import GNSS_SYSTEMS, MultiGNSSConstellation
from utils import lla_to_ecef

LAT, LON, ALT = 45.815, 15.982, 120.0


def isb(b):
    rng = np.random.default_rng(9)
    con = MultiGNSSConstellation(rng=rng)
    gt = np.array(lla_to_ecef(LAT, LON, ALT))
    rx = Receiver(gt, rng=rng)
    T = 600
    est = {s: [] for s in ISB_INDEX}
    sig = {s: [] for s in ISB_INDEX}
    err = []
    for t in range(T):
        con.update_all(float(t))
        rx.receive_signals(con, float(t))
        p, _ = rx.solve_position()
        for s, k in ISB_INDEX.items():
            est[s].append(rx.x_ekf[k] if p is not None else np.nan)
            sig[s].append(np.sqrt(rx.P_ekf[k, k]) if p is not None else np.nan)
        err.append(np.linalg.norm(p - gt) if p is not None else np.nan)
    t = np.arange(T)
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    imena = {"GAL": "Galileo", "GLO": "GLONASS", "BDS": "BeiDou"}
    for s in ISB_INDEX:
        e, sg = np.array(est[s]), np.array(sig[s])
        ax.plot(t, e, color=SUSTAVI[s], lw=1.2, label=f"{imena[s]} (procjena)")
        ax.fill_between(t, e - 2 * sg, e + 2 * sg, color=SUSTAVI[s], alpha=0.12, linewidth=0)
        ax.axhline(GNSS_SYSTEMS[s]["isb_m"], color=SUSTAVI[s], lw=0.8, ls="--")
    ax.set_xlabel("vrijeme od hladnog starta [s]")
    ax.set_ylabel("ISB u odnosu na GPS [m]")
    ax.set_ylim(-20, 35)
    ax.legend(ncol=3, loc="upper center", fontsize=7.5)
    decimalni_zarez(ax)
    spremi(fig, "09-isb")
    b["isb_istina"] = {s: GNSS_SYSTEMS[s]["isb_m"] for s in ISB_INDEX}
    b["isb_kraj"] = {s: round(float(est[s][-1]), 2) for s in ISB_INDEX}
    b["isb_sigma_kraj"] = {s: round(float(sig[s][-1]), 2) for s in ISB_INDEX}
    b["isb_sred_zadnjih_300"] = {s: round(float(np.nanmean(est[s][300:])), 2) for s in ISB_INDEX}
    b["isb_err3d_med"] = round(float(np.nanmedian(err[60:])), 2)


def _v(p, m, k=1.0):
    v = p[m]["mean"]
    return np.nan if v is None else k * v


def studija(b):
    r = ucitaj_studiju("multignss_mask")
    if r is None:
        return
    skupovi = {("GPS",): "GPS", ("GPS", "GAL"): "GPS+Galileo", ("GPS", "GAL", "GLO", "BDS"): "četiri sustava"}
    boje = {"GPS": SUSTAVI["GPS"], "GPS+Galileo": SUSTAVI["GAL"], "četiri sustava": "black"}
    met = ("availability", "integrity_availability", "hpl_median", "h_err_p95", "gdop_median", "n_sats_mean")
    out = {}
    for sk, ime in skupovi.items():
        r3 = lambda v: None if v is None else round(v, 3)  # noqa: E731  (nema fixa -> nema HPL-a)
        out[ime] = [dict(x=p["x"], **{m: {"mean": r3(p[m]["mean"]), "ci": [r3(c) for c in p[m]["ci"]]} for m in met})
                    for p in agregat(r, met, "mask_deg", filtar=lambda par, sk=sk: tuple(par["systems"]) == sk)]
    b["studija"] = out
    fig, axs = plt.subplots(1, 3, figsize=(7.0, 2.6))
    for ime, niz in out.items():
        x = [p["x"] for p in niz]
        axs[0].plot(x, [_v(p, "n_sats_mean") for p in niz], "o-", ms=3, color=boje[ime], label=ime)
        axs[1].plot(x, [_v(p, "hpl_median") for p in niz], "o-", ms=3, color=boje[ime])
        axs[2].plot(x, [_v(p, "integrity_availability", 100) for p in niz], "o-", ms=3, color=boje[ime])
    axs[0].set_ylabel("satelita u rješenju")
    axs[1].set_ylabel("medijan HPL [m]")
    axs[1].set_yscale("log")
    axs[2].set_ylabel("HPL ≤ 100 m [% epoha]")
    for ax in axs:
        ax.set_xlabel("maska [°]")
        decimalni_zarez(ax) if ax is not axs[1] else None
    axs[0].legend(fontsize=7)
    spremi(fig, "09-studija")


def main():
    b = {}
    isb(b)
    studija(b)
    with open(os.path.join(UDZBENIK, "skripte", "brojke_09.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in b.items() if k != "studija"}, indent=1, ensure_ascii=False))
    for ime, niz in b.get("studija", {}).items():
        print(ime, [(p["x"], p["hpl_median"]["mean"], p["integrity_availability"]["mean"],
                     p["availability"]["mean"], p["h_err_p95"]["mean"], p["n_sats_mean"]["mean"]) for p in niz])


if __name__ == "__main__":
    main()
