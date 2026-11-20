"""Poglavlje 4 — signal: Gold kodovi, korelacija i DLL, C/N0 iz link budgeta, šum koda."""
import json
import os

import numpy as np

from stil import CRVENA, NARANCASTA, PLAVA, SIVA, SUSTAVI, UDZBENIK, ZELENA, decimalni_zarez, plt, spremi

import signal_model as sm
import signal_processing as sp
from physics_engine import C, R_EARTH
from realdata import enu_basis
from satellite import GNSS_SYSTEMS, WalkerDeltaConstellation
from utils import lla_to_ecef

F1, F2 = 1575.42e6, 1227.60e6
RX = np.array(lla_to_ecef(45.815, 15.982, 120.0))


def kruzna_korelacija(a, b):
    return np.real(np.fft.ifft(np.fft.fft(a) * np.conj(np.fft.fft(b))))


def gold():
    a, b = sp.gold_code(5), sp.gold_code(300)
    ak = kruzna_korelacija(a, a)
    xk = kruzna_korelacija(a, b)
    rng = np.random.default_rng(1)
    ra, rb = rng.choice([-1.0, 1.0], 1023), rng.choice([-1.0, 1.0], 1023)
    rx = kruzna_korelacija(ra, rb)
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.8))
    pom = np.arange(-511, 512)
    axs[0].plot(pom, np.roll(ak, 511), color=PLAVA, lw=0.8)
    axs[0].set_title("autokorelacija (isti kod)")
    axs[0].set_xlabel("pomak [čip]")
    axs[0].set_xlim(-511, 511)
    axs[0].annotate("1023", (0, 1023), xytext=(60, 900), fontsize=7.5, arrowprops=dict(arrowstyle="-", lw=0.6))
    k = np.arange(0, 120)
    axs[1].step(k, rx[k], where="mid", color=SIVA, lw=0.8, label="slučajni ±1 nizovi")
    axs[1].step(k, xk[k], where="mid", color=NARANCASTA, lw=1.0, label="dva Gold koda")
    for v in (-65, -1, 63):
        axs[1].axhline(v, color="black", lw=0.5, ls=":")
    axs[1].set_title("međukorelacija (prvih 120 pomaka)")
    axs[1].set_xlabel("pomak [čip]")
    axs[1].set_xlim(0, 119)
    axs[1].legend(loc="lower right", fontsize=7, frameon=True)
    spremi(fig, "04-gold")
    return dict(gold_vrijednosti=sorted(int(round(v)) for v in set(np.round(xk))),
                gold_max=int(round(np.max(np.abs(xk)))), slucajni_max=int(round(np.max(np.abs(rx)))),
                auto_vrh=int(round(ak[0])), auto_ostalo=sorted(set(int(round(v)) for v in ak[1:])))


def dll():
    tau = np.linspace(-1.75, 1.75, 701)
    R = np.clip(1 - np.abs(tau), 0, None)
    d = sm.DLL_SPACING_CHIPS
    Re = np.clip(1 - np.abs(tau + d / 2), 0, None)
    Rl = np.clip(1 - np.abs(tau - d / 2), 0, None)
    D = Re ** 2 - Rl ** 2
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.7))
    axs[0].plot(tau, R, color=PLAVA, label="točni (P)")
    axs[0].plot(tau, Re, color=ZELENA, ls="--", lw=1, label="rani (E)")
    axs[0].plot(tau, Rl, color=NARANCASTA, ls="--", lw=1, label="kasni (L)")
    axs[0].set_xlabel("pogreška kašnjenja τ [čip]")
    axs[0].set_title("korelacijska funkcija")
    axs[0].legend(fontsize=7)
    axs[1].plot(tau, D, color=CRVENA)
    axs[1].axhline(0, color="black", lw=0.5)
    axs[1].axvline(0, color="black", lw=0.5)
    axs[1].set_xlabel("pogreška kašnjenja τ [čip]")
    axs[1].set_title(f"diskriminator E−L (d = {d:g} čipa)".replace(".", ","))
    for ax in axs:
        decimalni_zarez(ax)
    spremi(fig, "04-dll")


def sat_na_elevaciji(el_deg, alt):
    """Položaj satelita na zadanoj elevaciji (azimut jug) i visini orbite iznad sfere R."""
    e, n, u = enu_basis(RX)
    el = np.radians(el_deg)
    smjer = np.cos(el) * (-n) + np.sin(el) * u
    rs = R_EARTH + alt
    r = np.linalg.norm(RX)
    b = 2 * RX @ smjer
    c = r * r - rs * rs
    d = (-b + np.sqrt(b * b - 4 * c)) / 2
    return RX + d * smjer


def cn0():
    el = np.linspace(2, 90, 89)
    fig, ax = plt.subplots(figsize=(6.2, 3.1))
    out = {}
    for sustav, boja in (("GPS", SUSTAVI["GPS"]), ("GAL", SUSTAVI["GAL"]), ("GLO", SUSTAVI["GLO"])):
        alt = GNSS_SYSTEMS[sustav]["alt"]
        l1 = [float(sm.cn0_dbhz(sat_na_elevaciji(e, alt), RX, "L1")[0]) for e in el]
        ax.plot(el, l1, color=boja, label=f"{sustav} L1")
        if sustav == "GPS":
            l2 = [float(sm.cn0_dbhz(sat_na_elevaciji(e, alt), RX, "L2")[0]) for e in el]
            ax.plot(el, l2, color=boja, ls="--", label="GPS L2")
            out["gps_l1_zenit"] = round(l1[-1], 1)
            out["gps_l1_5"] = round(float(np.interp(5, el, l1)), 1)
            out["gps_l1_30"] = round(float(np.interp(30, el, l1)), 1)
            out["gps_l2_zenit"] = round(l2[-1], 1)
        out[f"{sustav}_l1_zenit"] = round(l1[-1], 1)
    ax.axhline(sm.TRACK_THRESHOLD_DBHZ, color="black", lw=0.8, ls=":")
    ax.text(3, sm.TRACK_THRESHOLD_DBHZ + 0.6, "prag zabrave (28 dB-Hz)", fontsize=7.5)
    ax.set_ylim(26, 52)
    ax.set_xlabel("elevacija [°]")
    ax.set_ylabel("C/N0 [dB-Hz]")
    ax.set_xlim(0, 90)
    ax.legend(ncol=2, fontsize=7.5, loc="center right")
    decimalni_zarez(ax)
    spremi(fig, "04-cn0")
    return out


def sum_koda():
    cn = np.linspace(28, 52, 100)
    s1 = sm.dll_sigma_m(cn)
    c1 = F1 ** 2 / (F1 ** 2 - F2 ** 2)
    c2 = F2 ** 2 / (F1 ** 2 - F2 ** 2)
    sif = np.hypot(c1 * s1, c2 * sm.dll_sigma_m(cn - 3.0))
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    ax.semilogy(cn, s1, color=PLAVA, label="L1 (jedna frekvencija)")
    ax.semilogy(cn, sif, color=NARANCASTA, label="iono-free L1/L2 (L2 3 dB slabiji)")
    ax.set_xlabel("C/N0 na L1 [dB-Hz]")
    ax.set_ylabel("σ šuma koda [m]")
    ax.legend()
    decimalni_zarez(ax)
    spremi(fig, "04-sum-koda")
    return dict(c_if1=round(c1, 3), c_if2=round(c2, 3), pojacanje_if=round(float(np.hypot(c1, c2)), 2))


def doppler():
    con = WalkerDeltaConstellation(rng=np.random.default_rng(0))
    mx = 0.0
    for t in np.arange(0, 43200, 120.0):
        con.update_all(t)
        for s in con.satellites:
            los = s.current_pos - RX
            if los @ RX / (np.linalg.norm(los) * np.linalg.norm(RX)) < np.sin(np.radians(5)):
                continue
            from physics_engine import calculate_orbital_position
            p1, _ = calculate_orbital_position(s.a, s.e, s.i, s.lan, s.w, s.m0, t + 0.5)
            p0, _ = calculate_orbital_position(s.a, s.e, s.i, s.lan, s.w, s.m0, t - 0.5)
            mx = max(mx, abs(float(sm.doppler_hz(s.current_pos, p1 - p0, RX, np.zeros(3), F1))))
    return round(mx, 0)


def main():
    b = {"cip_m": round(sp.METERS_PER_CHIP, 1), "N0_dbw_hz": round(float(sm.N0_DBW_HZ), 1)}
    b.update(gold())
    dll()
    b.update(cn0())
    b.update(sum_koda())
    for cnv in (49.0, 45.0, 39.0, 30.0):
        b[f"sigma_l1_{int(cnv)}"] = round(float(sm.dll_sigma_m(cnv)), 2)
    b["doppler_max_hz"] = doppler()
    b["jam_10db"] = round(sm.jam_loss_db(10.0), 1)
    b["jam_20db"] = round(sm.jam_loss_db(20.0), 1)
    b["koh_25hz"] = round(float(sm.coherent_gain(25.0)), 3)
    b["mai_sred_db"] = round(float(10 * np.log10(sm.X_MS / sm.LINE_SPACING_HZ)), 1)
    with open(os.path.join(UDZBENIK, "skripte", "brojke_04.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps(b, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
