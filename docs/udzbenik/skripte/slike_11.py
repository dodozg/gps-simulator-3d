"""Poglavlje 11 — RTK: float vs fix kroz vrijeme, vrijeme do fiksa po sustavima i duljini baze."""
import json
import os

import numpy as np

from stil import NARANCASTA, PLAVA, SIVA, UDZBENIK, ZELENA, CRVENA, decimalni_zarez, plt, spremi

import rtk
from realdata import enu_basis
from satellite import MultiGNSSConstellation
from utils import lla_to_ecef

LAT, LON, ALT = 45.815, 15.982, 120.0


def jedan_run(sustavi, baza_km, seed, T=900, korak=1.0):
    rover = np.array(lla_to_ecef(LAT, LON, ALT))
    e, n, u = enu_basis(rover)
    con = MultiGNSSConstellation(rng=np.random.default_rng(seed))
    live = rtk.LiveRTK(seed=seed)
    live.enabled = True
    live.set_base(rover + baza_km * 1000.0 * e, auto=False)
    t_l, err, ferr, st = [], [], [], []
    for k in range(int(T / korak)):
        t = k * korak
        con.update_all(t)
        sats = [s for s in con.satellites if s.system in sustavi]
        status = live.step(t, sats, rover, kinematic=False)
        rep = live.report(rover, t)
        t_l.append(t)
        err.append(rep["error_m"] if rep["error_m"] is not None else np.nan)
        ferr.append(rep["float_error_m"] if rep["float_error_m"] is not None else np.nan)
        st.append(status)
    rep = live.report(rover, T)
    return dict(t=np.array(t_l), err=np.array(err), ferr=np.array(ferr), st=np.array(st),
                ttf=rep["time_to_fix_s"], udio_fix=live.fixed_epochs / max(live.epochs, 1))


def tijek(b):
    a = jedan_run(("GPS", "GAL", "BDS"), 4.0, 3)
    g = jedan_run(("GPS",), 4.0, 3)
    fig, ax = plt.subplots(figsize=(6.4, 3.1))
    for r, boja, opis in ((a, PLAVA, "GPS + Galileo + BeiDou"), (g, NARANCASTA, "samo GPS")):
        ax.plot(r["t"], r["ferr"], color=boja, lw=0.8, alpha=0.6, ls="--")
        fiks = np.where(r["st"] == "fixed", r["err"], np.nan)
        ax.plot(r["t"], fiks, color=boja, lw=1.6, label=f"{opis}: FIX")
        ax.plot([], [], color=boja, lw=0.8, ls="--", label=f"{opis}: float")
    ax.set_yscale("log")
    ax.set_xlabel("vrijeme od uključivanja RTK-a [s]")
    ax.set_ylabel("3D pogreška [m]")
    ax.legend(fontsize=7, ncol=2, loc="upper right")
    spremi(fig, "11-tijek")
    def opis(r):
        m = r["st"] == "fixed"
        return dict(ttf=r["ttf"], udio_fix=round(float(r["udio_fix"]) * 100, 1),
                    fix_med_cm=round(float(np.nanmedian(r["err"][m])) * 100, 2) if m.any() else None,
                    float_kraj_cm=round(float(np.nanmedian(r["ferr"][-60:])) * 100, 1),
                    float_60s_m=round(float(np.nanmedian(r["ferr"][50:70])), 2))
    b["tijek"] = {"tri": opis(a), "gps": opis(g)}


def baze(b):
    duljine = [1, 5, 10, 20, 40]
    rez = []
    for km in duljine:
        ttf, ud, ef = [], [], []
        for seed in (11, 12, 13, 14):
            r = jedan_run(("GPS", "GAL", "BDS"), km, seed, T=600)
            ttf.append(np.nan if r["ttf"] is None else r["ttf"])
            ud.append(r["udio_fix"])
            m = r["st"] == "fixed"
            ef.append(np.nanmedian(r["err"][m]) if m.any() else np.nan)
        rez.append(dict(km=km, ttf_med=None if np.all(np.isnan(ttf)) else round(float(np.nanmedian(ttf)), 0),
                        ttf_sve=[None if np.isnan(x) else round(float(x), 0) for x in ttf],
                        udio_fix=round(float(np.mean(ud)) * 100, 1),
                        fix_err_cm=None if np.all(np.isnan(ef)) else round(float(np.nanmedian(ef)) * 100, 2)))
    b["baze"] = rez
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.8))
    axs[0].plot(duljine, [np.nan if r["ttf_med"] is None else r["ttf_med"] for r in rez], "o-", color=PLAVA)
    axs[0].set_xlabel("duljina baze [km]")
    axs[0].set_ylabel("vrijeme do FIX-a [s] (medijan)")
    axs[0].set_ylim(0, None)
    axs[1].plot(duljine, [r["udio_fix"] for r in rez], "o-", color=ZELENA)
    axs[1].set_xlabel("duljina baze [km]")
    axs[1].set_ylabel("epohe s FIX-om [%]")
    axs[1].set_ylim(0, 105)
    for ax in axs:
        decimalni_zarez(ax)
    spremi(fig, "11-baze")


def main():
    b = {"lambda_cm": round(rtk.LAMBDA1 * 100, 2), "faza_mm": rtk.PHASE_SIGMA_M * 1000,
         "kod_m": rtk.LIVE_CODE_SIGMA_M, "atmo_ppm": rtk.ATMO_PPM, "ratio_min": rtk.RATIO_MIN,
         "p_boot": rtk.P_BOOT_MIN, "maska": rtk.LIVE_MASK_DEG}
    tijek(b)
    baze(b)
    with open(os.path.join(UDZBENIK, "skripte", "brojke_11.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps(b, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
