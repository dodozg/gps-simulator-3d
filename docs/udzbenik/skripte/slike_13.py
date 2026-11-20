"""Poglavlje 13 — pravi podaci: SPP na GEONET 0759 (EKF vs LS) i emitirane vs precizne IGS orbite."""
import json
import os

import numpy as np

from stil import NARANCASTA, PLAVA, SIVA, UDZBENIK, decimalni_zarez, plt, spremi

import ephemeris as ep
import realdata
import rinex

DATA = os.path.join(os.path.dirname(os.path.dirname(UDZBENIK)), "tests", "data")


def spp(b):
    obs = rinex.read_obs(realdata.SAMPLE_OBS)
    nav = rinex.read_nav(realdata.SAMPLE_NAV)
    res = realdata.process(obs, nav, mask_deg=realdata.DEFAULT_MASK_DEG, solver="ekf")
    rows = res["rows"]
    t = np.array([r["t"] for r in rows]) / 60.0
    enu = np.array([r["enu"] if r["enu"] is not None else [np.nan] * 3 for r in rows])
    lse = np.array([r["ls_enu"] if r["ls_enu"] is not None else [np.nan] * 3 for r in rows])
    fig, axs = plt.subplots(2, 1, figsize=(6.4, 3.8), sharex=True)
    axs[0].plot(t, np.hypot(lse[:, 0], lse[:, 1]), color=NARANCASTA, lw=1, label="LS (snapshot)")
    axs[0].plot(t, np.hypot(enu[:, 0], enu[:, 1]), color=PLAVA, lw=1.3, label="EKF + RAIM")
    axs[0].set_ylabel("horizontalno [m]")
    axs[0].legend()
    axs[1].plot(t, lse[:, 2], color=NARANCASTA, lw=1)
    axs[1].plot(t, enu[:, 2], color=PLAVA, lw=1.3)
    axs[1].axhline(0, color="black", lw=0.5)
    axs[1].set_ylabel("vertikalno [m]")
    axs[1].set_xlabel("vrijeme od 2005-04-02 00:00 GPST [min]")
    for ax in axs:
        decimalni_zarez(ax)
    spremi(fig, "13-spp")
    s, l = res["summary"], res["ls_summary"]
    gd = [r.get("gdop") for r in rows if r.get("gdop") is not None]
    b["spp"] = dict(stanica=res["station"], prijemnik=res["receiver"], epoha=res["n_epochs"], rijeseno=res["solved"],
                    maska=res["mask_deg"], ekf=dict(h_med=round(s["h_median"], 2), h_p95=round(s["h_p95"], 2),
                                                    v_med=round(s["v_median"], 2), v_p95=round(s["v_p95"], 2),
                                                    sred=[round(x, 2) for x in s["mean_enu"]]),
                    ls=dict(h_med=round(l["h_median"], 2), h_p95=round(l["h_p95"], 2),
                            v_med=round(l["v_median"], 2), v_p95=round(l["v_p95"], 2)),
                    alarmi=len(res["raim_alarms"]), gdop_med=round(float(np.median(gd)), 2) if gd else None,
                    n_sat_med=int(np.median([len(r.get("sats", [])) for r in rows])) if rows and "sats" in rows[0] else None)


def mali_q(b):
    """EKF ≈ LS uz 30 s razmak epoha; s 1000× manjim procesnim šumom predikcija opet nosi informaciju."""
    import receiver as rmod
    obs = rinex.read_obs(realdata.SAMPLE_OBS)
    nav = rinex.read_nav(realdata.SAMPLE_NAV)
    res = realdata.process(obs, nav)
    d = [np.linalg.norm(r["enu"] - r["ls_enu"]) for r in res["rows"] if r["enu"] is not None and r["ls_enu"] is not None]
    izv = (rmod.Q_POS, rmod.Q_VEL)
    try:
        rmod.Q_POS, rmod.Q_VEL = izv[0] / 1000, izv[1] / 1000
        s = realdata.process(obs, nav)["summary"]
    finally:
        rmod.Q_POS, rmod.Q_VEL = izv
    from utils import ecef_to_lla
    b["stanica_lla"] = [round(float(v), 3) for v in ecef_to_lla(*realdata.reference_position(obs))]
    s25 = realdata.process(obs, nav, mask_deg=25)["summary"]
    b["maska25"] = dict(h_med=round(s25["h_median"], 2), h_p95=round(s25["h_p95"], 2), v_med=round(s25["v_median"], 2), v_p95=round(s25["v_p95"], 2))
    b["ekf_ls_max_razlika_mm"] = round(1000 * float(max(d)), 1)
    b["mali_q"] = dict(h_med=round(s["h_median"], 2), h_p95=round(s["h_p95"], 2), v_med=round(s["v_median"], 2), v_p95=round(s["v_p95"], 2))


def efemeride(b):
    brdc = rinex.read_nav(os.path.join(DATA, "brdc1820_trim.10n"))
    sp3 = rinex.read_sp3(os.path.join(DATA, "igs15904_trim.sp3"))
    d_pos, d_clk, d_rad, d_uz, d_pop = [], [], [], [], []
    for sat, recs in sp3.items():
        for t, xyz, clk in recs:
            eph = ep.select_ephemeris(brdc.ephemerides.get(sat, []), t)
            if eph is None:
                continue
            p, _ = ep.sat_position(eph, t)
            d = p - xyz
            d_pos.append(float(np.linalg.norm(d)))
            r = xyz / np.linalg.norm(xyz)
            c = np.cross(xyz, ep.sat_velocity(eph, t))
            c = c / np.linalg.norm(c)
            d_rad.append(float(d @ r))
            d_uz.append(float(d @ np.cross(c, r)))
            d_pop.append(float(d @ c))
            if np.isfinite(clk):
                d_clk.append((ep.sat_clock(eph, t, include_relativity=False) - clk) * ep.C_LIGHT)
    d_pos, d_clk, d_rad = map(np.array, (d_pos, d_clk, d_rad))
    d_clk = d_clk - np.median(d_clk)      # zajednički pomak (referenca satova) ne utječe na položaj
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.7))
    axs[0].hist(d_pos, bins=30, color=PLAVA, alpha=0.7)
    axs[0].set_xlabel("|emitirana − precizna| položaj [m]")
    axs[0].set_ylabel("broj")
    axs[1].hist(d_clk, bins=30, color=NARANCASTA, alpha=0.7)
    axs[1].set_xlabel("sat: emitirani − precizni [m]")
    for ax in axs:
        decimalni_zarez(ax)
    spremi(fig, "13-efemeride")
    b["eph"] = dict(n=int(len(d_pos)), med=round(float(np.median(d_pos)), 2), p95=round(float(np.percentile(d_pos, 95)), 2),
                    max=round(float(d_pos.max()), 2), rad_std=round(float(np.std(d_rad)), 2),
                    uz_std=round(float(np.std(d_uz)), 2), pop_std=round(float(np.std(d_pop)), 2),
                    clk_std=round(float(np.std(d_clk)), 2), n_sat=len([k for k, v in sp3.items() if v]))


def main():
    b = {}
    spp(b)
    mali_q(b)
    efemeride(b)
    with open(os.path.join(UDZBENIK, "skripte", "brojke_13.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps(b, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
