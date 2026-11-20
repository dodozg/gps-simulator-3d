"""Poglavlje 7 — geometrija i DOP: DOP kroz dan, pogreška ∝ DOP, studije broja satelita i maske."""
import json
import os

import numpy as np

from stil import CRVENA, NARANCASTA, PLAVA, SIVA, UDZBENIK, ZELENA, agregat, decimalni_zarez, plt, spremi, ucitaj_studiju

from physics_engine import calculate_sagnac_correction
from realdata import az_el, enu_basis, to_enu
from receiver import Receiver, meas_sigma
from satellite import WalkerDeltaConstellation
from utils import lla_to_ecef

LAT, LON, ALT = 45.815, 15.982, 120.0
REZ = os.path.join(UDZBENIK, "studije", "rezultati")


def dop_iz_smjerova(az, el):
    """Q = (GᵀG)⁻¹ u ENU + sat. Redak: (−e_E, −e_N, −e_U, 1)."""
    G = np.column_stack([-np.cos(el) * np.sin(az), -np.cos(el) * np.cos(az), -np.sin(el), np.ones_like(az)])
    Q = np.linalg.inv(G.T @ G)
    d = np.diag(Q)
    return dict(G=float(np.sqrt(d.sum())), P=float(np.sqrt(d[:3].sum())), H=float(np.sqrt(d[0] + d[1])),
                V=float(np.sqrt(d[2])), T=float(np.sqrt(d[3])), E=float(np.sqrt(d[0])), N=float(np.sqrt(d[1])))


def dop_kroz_dan(b):
    out = {}
    for ime, la, lo in (("Zagreb", LAT, LON), ("Quito", -0.18, -78.47)):
        rx = np.array(lla_to_ecef(la, lo, 0.0))
        con = WalkerDeltaConstellation(rng=np.random.default_rng(0))
        t = np.arange(0.0, 86400.0, 120.0)
        niz = []
        for tt in t:
            con.update_all(tt)
            ae = [az_el(rx, s.current_pos) for s in con.satellites]
            ae = np.array([x for x in ae if np.degrees(x[1]) >= 5.0])
            d = dop_iz_smjerova(ae[:, 0], ae[:, 1])
            d["n"] = len(ae)
            niz.append(d)
        out[ime] = (t, niz)
    t, niz = out["Zagreb"]
    fig, ax = plt.subplots(figsize=(6.4, 3.1))
    for k, boja in (("G", "black"), ("P", PLAVA), ("V", NARANCASTA), ("H", ZELENA)):
        ax.plot(t / 3600, [d[k] for d in niz], color=boja, lw=1.1, label=f"{k}DOP")
    ax.set_xlabel("vrijeme [h]")
    ax.set_ylabel("DOP")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_ylim(0, 4.2)          # mjesto za legendu iznad krivulja
    ax2 = ax.twinx()
    ax2.step(t / 3600, [d["n"] for d in niz], where="mid", color=SIVA, lw=0.8, alpha=0.7)
    ax2.set_ylabel("broj satelita (sivo)", color=SIVA)
    ax2.set_ylim(0, 14)
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    ax.legend(ncol=4, loc="upper left")
    decimalni_zarez(ax)
    spremi(fig, "07-dop-dan")
    for ime, (t, niz) in out.items():
        b[f"dop_{ime}"] = {k: dict(med=round(float(np.median([d[k] for d in niz])), 2),
                                   max=round(float(np.max([d[k] for d in niz])), 2)) for k in ("G", "P", "H", "V", "T")}
        b[f"dop_{ime}"]["N_E_omjer"] = round(float(np.median([d["N"] / d["E"] for d in niz])), 2)
        b[f"dop_{ime}"]["n_min"] = int(min(d["n"] for d in niz))
        b[f"dop_{ime}"]["n_max"] = int(max(d["n"] for d in niz))


def pogreska_vs_hdop(b):
    """Snapshot LS na slučajnim podskupovima satelita: horizontalna pogreška raste s HDOP-om."""
    rng = np.random.default_rng(7)
    con = WalkerDeltaConstellation(rng=rng)
    for s in con.satellites:
        s.is_spoofed = False
    rx = np.array(lla_to_ecef(LAT, LON, ALT))
    rcv = Receiver(rx, rng=rng)
    izbor = np.random.default_rng(11)
    hd, eh, vd, ev = [], [], [], []
    x = np.r_[rx + 50.0, 0.0]
    for t in range(0, 3000, 2):
        con.update_all(float(t))
        sig = rcv.receive_signals(con, float(t))
        rcv.solve_position()
        if len(sig) < 5:
            continue
        k = int(izbor.integers(4, len(sig) + 1))
        pod = [sig[i] for i in izbor.choice(len(sig), k, replace=False)]
        xx = np.r_[rx + 50.0, x[3]]
        for _ in range(6):
            G, y = [], []
            for s in pod:
                dv = xx[:3] - s["broadcast_pos"]
                r = np.linalg.norm(dv)
                y.append(s["pseudorange"] - (r + xx[3] + calculate_sagnac_correction(s["broadcast_pos"], xx[:3])))
                G.append([*(dv / r), 1.0])
            xx = xx + np.linalg.lstsq(np.array(G), np.array(y), rcond=None)[0]
        x = xx
        ae = np.array([az_el(rx, s["broadcast_pos"]) for s in pod])
        d = dop_iz_smjerova(ae[:, 0], ae[:, 1])
        e = to_enu(xx[:3] - rx, rx)
        hd.append(d["H"])
        eh.append(float(np.hypot(e[0], e[1])))
        vd.append(d["V"])
        ev.append(abs(float(e[2])))
    hd, eh, vd, ev = map(np.array, (hd, eh, vd, ev))
    # σ_H ≈ HDOP·σ_UERE. Robusno: za izotropnu 2D Gaussovu pogrešku je medijan (e_H/HDOP)² = σ²·ln 2.
    n_sve = len(hd)
    m20 = hd <= 20.0
    udio_singular = float(np.mean(hd > 20.0))
    hd, eh = hd[m20], eh[m20]
    uere = float(np.sqrt(np.median((eh / hd) ** 2) / np.log(2.0)))
    rub = np.quantile(hd, np.linspace(0, 1, 9))
    sred, rms = [], []
    for a, c in zip(rub[:-1], rub[1:]):
        m = (hd >= a) & (hd <= c)
        sred.append(np.median(hd[m]))
        rms.append(np.sqrt(np.median(eh[m] ** 2) / np.log(2.0)))
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    ax.scatter(hd, eh, s=3, alpha=0.25, color=PLAVA, linewidths=0, label="epohe (slučajni podskup 4–n satelita)")
    ax.plot(sred, rms, "o-", color=CRVENA, ms=4, label="σ po razredu HDOP-a (robusno)")
    xs = np.linspace(hd.min(), np.quantile(hd, 0.98), 50)
    ax.plot(xs, uere * xs, "--", color="black", lw=1, label=f"HDOP × {uere:.1f} m".replace(".", ","))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("HDOP")
    ax.set_ylabel("horizontalna pogreška [m]")
    ax.legend(loc="lower right", markerscale=4, frameon=True)
    spremi(fig, "07-pogreska-hdop")
    b.update(uere_iz_hdop=round(uere, 2), hdop_raspon=[round(float(hd.min()), 2), round(float(np.quantile(hd, 0.98)), 1)],
             n_epoha_hdop=n_sve, udio_hdop_iznad_20=round(100 * udio_singular, 1))


def primjeri_geometrije(b):
    """Četiri satelita: jedan u zenitu + tri na horizontu vs. četiri zbijena oko zenita."""
    dobra = dop_iz_smjerova(np.radians([0, 0, 120, 240]), np.radians([90, 0, 0, 0]))
    dobra5 = dop_iz_smjerova(np.radians([0, 0, 120, 240]), np.radians([90, 5, 5, 5]))
    losa = dop_iz_smjerova(np.radians([0, 0, 120, 240]), np.radians([90, 80, 80, 80]))
    b["primjer_dobra"] = {k: round(v, 2) for k, v in dobra.items() if k in "GPHVT"}
    b["primjer_dobra5"] = {k: round(v, 2) for k, v in dobra5.items() if k in "GPHVT"}
    b["primjer_losa"] = {k: round(v, 1) for k, v in losa.items() if k in "GPHVT"}


def studije(b):
    r = ucitaj_studiju("max_sats")
    m = ucitaj_studiju("maska")
    if r is None or m is None:
        return
    b["studija_max_sats"] = agregat(r, ("h_err_p95", "v_err_p95", "gdop_median", "n_sats_mean"), "max_sats")
    b["studija_maska"] = agregat(m, ("availability", "h_err_p95", "v_err_p95", "gdop_median", "n_sats_mean"), "mask_deg")
    fig, axs = plt.subplots(1, 2, figsize=(6.8, 2.9))
    for ax, s, x, naslov in ((axs[0], b["studija_max_sats"], "max_sats", "četiri sustava: najviše satelita u rješenju"),
                             (axs[1], b["studija_maska"], "mask_deg", "samo GPS: elevacijska maska [°]")):
        xs = [p["x"] for p in s]
        for k, boja, opis in (("h_err_p95", PLAVA, "horiz. p95"), ("v_err_p95", NARANCASTA, "vert. p95")):
            y = np.array([p[k]["mean"] for p in s])
            lo = np.array([p[k]["ci"][0] for p in s])
            hi = np.array([p[k]["ci"][1] for p in s])
            ax.plot(xs, y, "o-", color=boja, ms=3.5, label=opis)
            ax.fill_between(xs, lo, hi, color=boja, alpha=0.18, linewidth=0)
        ax.set_title(naslov, fontsize=8.5)
        ax.set_ylabel("pogreška [m]")
        ax.set_ylim(0, None)
        decimalni_zarez(ax)
    axs[0].set_xlabel("max_sats")
    axs[1].set_xlabel("maska [°]")
    axs[0].legend()
    spremi(fig, "07-studije")


def main():
    b = {}
    dop_kroz_dan(b)
    pogreska_vs_hdop(b)
    primjeri_geometrije(b)
    studije(b)
    with open(os.path.join(UDZBENIK, "skripte", "brojke_07.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in b.items() if not k.startswith("studija")}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
