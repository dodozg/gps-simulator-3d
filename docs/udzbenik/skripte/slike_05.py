"""Poglavlje 5 — izvori pogrešaka: ionosfera kroz dan, ostatak pogreške mjerenja po elevaciji, efemeride."""
import json
import os

import numpy as np

from stil import NARANCASTA, PLAVA, SIVA, UDZBENIK, ZELENA, CRVENA, decimalni_zarez, plt, spremi

import iono
from physics_engine import C, calculate_sagnac_correction, calculate_tropospheric_delay
from realdata import az_el
from receiver import Receiver, meas_sigma
from satellite import WalkerDeltaConstellation
from utils import lla_to_ecef

LAT, LON, ALT = 45.815, 15.982, 120.0
SJEME = 5


def ionosfera(b):
    sati, dz = iono.diurnal(LAT, LON, n=289)
    tow_podne = (50400.0 - 43200.0 * (LON / 180.0)) % 86400.0
    tow_noc = (tow_podne + 43200.0) % 86400.0
    el = np.linspace(5, 90, 86)
    podne = [iono.slant_delay_m(LAT, LON, np.radians(e), np.pi, tow_podne) for e in el]
    noc = [iono.slant_delay_m(LAT, LON, np.radians(e), np.pi, tow_noc) for e in el]
    l2 = [iono.slant_delay_m(LAT, LON, np.radians(e), np.pi, tow_podne, iono.F_L2) for e in el]
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.8))
    axs[0].plot(sati, dz, color=PLAVA)
    axs[0].set_xlabel("lokalno vrijeme [h]")
    axs[0].set_ylabel("zenitno kašnjenje L1 [m]")
    axs[0].set_xlim(0, 24)
    axs[0].set_xticks(range(0, 25, 6))
    axs[1].plot(el, podne, color=PLAVA, label="L1, 14 h")
    axs[1].plot(el, l2, color=NARANCASTA, label="L2, 14 h")
    axs[1].plot(el, noc, color=SIVA, label="L1, noć")
    axs[1].set_xlabel("elevacija [°]")
    axs[1].set_ylabel("koso kašnjenje [m]")
    axs[1].legend()
    for ax in axs:
        decimalni_zarez(ax)
    spremi(fig, "05-ionosfera")
    k = int(np.argmax(dz))
    b.update(iono_vrh_m=round(float(dz[k]), 2), iono_vrh_h=round(float(sati[k]), 1),
             iono_noc_m=round(float(dz.min()), 2),
             iono_l1_5_podne=round(float(podne[0]), 1), iono_l1_20_podne=round(float(np.interp(20, el, podne)), 1),
             iono_l2_l1_omjer=round(float(l2[0] / podne[0]), 3),
             iono_if_ostatak_m=float(abs(iono.iono_free_residual_m(LAT, LON, np.radians(20), np.pi, tow_podne))))


def ostatak(b):
    rng = np.random.default_rng(SJEME)
    con = WalkerDeltaConstellation(rng=rng)
    for s in con.satellites:
        s.is_spoofed = False
    rx = np.array(lla_to_ecef(LAT, LON, ALT))
    rcv = Receiver(rx, rng=rng)
    el_l, ost_l, sig_l, eph_l = [], [], [], []
    eph_niz = {}
    for t in range(0, 4 * 3600, 5):
        con.update_all(float(t))
        sig = rcv.receive_signals(con, float(t))
        rcv.solve_position()
        for s in sig:
            _, e = az_el(rx, s["sat_pos"])
            ost = (s["pseudorange"] - s["true_dist"] - rcv.meas.clock_bias * C
                   - calculate_sagnac_correction(s["sat_pos"], rx))
            u = (s["sat_pos"] - rx) / np.linalg.norm(s["sat_pos"] - rx)
            eph = float((s["broadcast_pos"] - s["sat_pos"]) @ u)
            el_l.append(np.degrees(e))
            ost_l.append(ost)
            sig_l.append(meas_sigma(s, np.sin(e)))
            eph_l.append(eph)
            if t % 60 == 0:
                eph_niz.setdefault(s["sat_id"], []).append((t, eph))
    el_l, ost_l, sig_l, eph_l = map(np.array, (el_l, ost_l, sig_l, eph_l))

    fig, ax = plt.subplots(figsize=(6.2, 3.1))
    ax.scatter(el_l[::3], ost_l[::3], s=2, alpha=0.25, color=PLAVA, linewidths=0, label="ostatak pogreške mjerenja")
    rubovi = np.arange(5, 95, 5)
    sred = 0.5 * (rubovi[1:] + rubovi[:-1])
    std = [np.std(ost_l[(el_l >= a) & (el_l < c)]) if np.sum((el_l >= a) & (el_l < c)) > 30 else np.nan
           for a, c in zip(rubovi[:-1], rubovi[1:])]
    mod = [np.median(sig_l[(el_l >= a) & (el_l < c)]) if np.sum((el_l >= a) & (el_l < c)) > 30 else np.nan
           for a, c in zip(rubovi[:-1], rubovi[1:])]
    ax.plot(sred, std, "o-", color=CRVENA, ms=3, label="izmjerena σ (po 5°)")
    ax.plot(sred, -np.array(std), "o-", color=CRVENA, ms=3)
    ax.plot(sred, mod, "--", color="black", lw=1, label="σ modela prijemnika")
    ax.plot(sred, -np.array(mod), "--", color="black", lw=1)
    ax.set_xlabel("elevacija [°]")
    ax.set_ylabel("pogreška pseudoudaljenosti [m]")
    ax.set_xlim(5, 90)
    lim = np.nanmax(mod) * 3
    ax.set_ylim(-lim, lim)
    ax.legend(loc="upper right", markerscale=4)
    decimalni_zarez(ax)
    spremi(fig, "05-ostatak")

    fig, ax = plt.subplots(figsize=(6.2, 2.6))
    duzi = sorted(eph_niz.items(), key=lambda kv: -len(kv[1]))[:4]
    for (sid, niz), boja in zip(duzi, (PLAVA, NARANCASTA, ZELENA, CRVENA)):
        tt, ee = np.array(niz).T
        ax.plot(tt / 60, ee, color=boja, lw=1.2, label=sid)
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("vrijeme [min]")
    ax.set_ylabel("pogreška efemerida duž LOS [m]")
    ax.legend(ncol=4, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.28))
    decimalni_zarez(ax)
    spremi(fig, "05-efemeride")

    def raspon(a, c):
        m = (el_l >= a) & (el_l < c)
        return dict(std=round(float(np.std(ost_l[m])), 2), sred=round(float(np.mean(ost_l[m])), 2),
                    model=round(float(np.median(sig_l[m])), 2), n=int(m.sum()))
    b.update(ost_5_15=raspon(5, 15), ost_15_30=raspon(15, 30), ost_30_60=raspon(30, 60), ost_60_90=raspon(60, 91),
             ost_sve_std=round(float(np.std(ost_l)), 2), ost_sve_sred=round(float(np.mean(ost_l)), 2),
             eph_los_std=round(float(np.std(eph_l)), 2))


def main():
    b = {}
    ionosfera(b)
    ostatak(b)
    rx = np.array(lla_to_ecef(LAT, LON, ALT))
    up = rx / np.linalg.norm(rx)
    b["tropo_zenit"] = round(float(calculate_tropospheric_delay(rx + up * 2.02e7, rx)), 2)
    b["tropo_5"] = round(2.4 / np.sin(np.radians(5)), 1)
    b["tropo_10"] = round(2.4 / np.sin(np.radians(10)), 1)
    f1, f2 = 1575.42e6, 1227.60e6
    b["if_k1"] = round(f1 ** 2 / (f1 ** 2 - f2 ** 2), 3)
    b["if_k2"] = round(f2 ** 2 / (f1 ** 2 - f2 ** 2), 3)
    b["tecu_l1_m"] = round(40.3e16 / f1 ** 2, 3)
    with open(os.path.join(UDZBENIK, "skripte", "brojke_05.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps(b, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
