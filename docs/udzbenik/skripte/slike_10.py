"""Poglavlje 10 — RAIM: χ² i prag, kalibracija testa, rampa kvara sa i bez RAIM-a, ROC studija."""
import json
import os

import numpy as np

from stil import CRVENA, NARANCASTA, PLAVA, SIVA, UDZBENIK, ZELENA, LJUBICASTA, agregat, decimalni_zarez, plt, spremi, ucitaj_studiju

import raim
from realdata import to_enu
from receiver import Receiver
from satellite import WalkerDeltaConstellation
from utils import lla_to_ecef

LAT, LON, ALT = 45.815, 15.982, 120.0


def pdf_iz_cdf(cdf, x):
    h = 1e-3
    return np.array([(cdf(v + h) - cdf(max(v - h, 0.0))) / (v + h - max(v - h, 0.0)) for v in x])


def razdiobe(b):
    dof = 4
    td = raim.chi2_isf(raim.RAIM_PFA, dof)
    lam = raim.noncentrality(dof, raim.RAIM_PFA, raim.RAIM_PMD)
    x = np.linspace(0.01, 140, 1400)
    p0 = pdf_iz_cdf(lambda v: raim.chi2_cdf(v, dof), x)
    p1 = pdf_iz_cdf(lambda v: raim.ncx2_cdf(v, dof, lam), x)
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    ax.plot(x, p0, color=PLAVA, label=f"bez kvara: χ²({dof})")
    ax.plot(x, p1, color=CRVENA, label=f"kvar: necentralni χ²({dof}, λ = {lam:.1f})".replace(".", ","))
    ax.axvline(td, color="black", lw=1, ls="--")
    ax.text(td + 1.5, max(p0) * 0.85, f"prag T_d = {td:.1f}\n(P_FA = 10⁻⁵)".replace(".", ","), fontsize=7.5)
    ax.fill_between(x, 0, p1, where=x < td, color=CRVENA, alpha=0.25, linewidth=0)
    ax.text(td - 27, 2e-6,"P_MD = 10⁻³\n(propušteno)", fontsize=7.5, color=CRVENA)
    ax.set_xlabel("testna statistika T")
    ax.set_ylabel("gustoća vjerojatnosti")
    ax.set_xlim(0, 140)
    ax.set_yscale("log")
    ax.set_ylim(1e-7, 0.3)
    ax.legend(loc="upper right")
    spremi(fig, "10-chi2")
    b["prag"] = {str(k): round(raim.chi2_isf(raim.RAIM_PFA, k), 2) for k in range(1, 9)}
    b["lambda"] = {str(k): round(raim.noncentrality(k, raim.RAIM_PFA, raim.RAIM_PMD), 1) for k in range(1, 9)}


def nova(seed):
    rng = np.random.default_rng(seed)
    con = WalkerDeltaConstellation(rng=rng)
    for s in con.satellites:
        s.is_spoofed = False
    gt = np.array(lla_to_ecef(LAT, LON, ALT))
    return con, Receiver(gt, rng=rng), gt


def kalibracija(b):
    """T u čistoj simulaciji (bez kvara) vs. χ² razdioba za najčešći dof."""
    T, D, omjer = [], [], []
    alarmi, epoha = 0, 0
    hpl = []
    for seed in (31, 32, 33):
        con, rx, gt = nova(seed)
        for t in range(0, 1800):
            con.update_all(float(t))
            rx.receive_signals(con, float(t))
            p, _ = rx.solve_position()
            ig = rx.integrity
            if p is None or ig.get("test") is None or t < 30:
                continue
            epoha += 1
            T.append(ig["test"])
            D.append(ig["dof"])
            omjer.append(ig["test"] / ig["threshold"])
            if ig.get("hpl") is not None:
                hpl.append(ig["hpl"])
            if ig["status"] in ("alarm", "excluded"):
                alarmi += 1
    T, D, omjer = np.array(T), np.array(D), np.array(omjer)
    vals, cnt = np.unique(D, return_counts=True)
    d0 = int(vals[np.argmax(cnt)])
    t0 = T[D == d0]
    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    ax.hist(t0, bins=60, range=(0, 25), density=True, color=PLAVA, alpha=0.5, label=f"simulacija (dof = {d0}, {len(t0)} epoha)")
    x = np.linspace(0.05, 25, 400)
    ax.plot(x, pdf_iz_cdf(lambda v: raim.chi2_cdf(v, d0), x), color="black", lw=1.2, label=f"χ²({d0})")
    ax.set_xlabel("testna statistika T")
    ax.set_ylabel("gustoća")
    ax.legend()
    decimalni_zarez(ax)
    spremi(fig, "10-kalibracija")
    b["kal"] = dict(epoha=epoha, dof=d0, n_dof=int(len(t0)), sred_T=round(float(t0.mean()), 2),
                    omjer_p50=round(float(np.percentile(omjer, 50)), 3), omjer_p99=round(float(np.percentile(omjer, 99)), 3),
                    omjer_max=round(float(omjer.max()), 3), alarmi_ili_iskljucenja=alarmi,
                    hpl_med=round(float(np.median(hpl)), 1), hpl_p95=round(float(np.percentile(hpl, 95)), 1))


def rampa(b):
    """Kvar sata jednog satelita raste 0,5 m/s od t = 120 s; EKF s RAIM-om i bez njega."""
    out = {}
    for ime, ukljucen in (("raim", True), ("bez", False)):
        con, rx, gt = nova(41)
        rx.raim_enabled = ukljucen
        meta = None
        t_l, eh, hpl, omj, iskl = [], [], [], [], []
        for t in range(0, 420):
            con.update_all(float(t))
            if t == 120:
                # pokvari satelit koji je najviše u rješenju (najveći utjecaj na položaj)
                ids = [s["sat_id"] for s in rx.received_signals]
                meta = next(s for s in con.satellites if s.sat_id == ids[0])
            if meta is not None:
                meta.user_clock_offset_m = 0.5 * (t - 120)
            rx.receive_signals(con, float(t))
            p, _ = rx.solve_position()
            if p is None:
                continue
            e = to_enu(p - gt, gt)
            ig = rx.integrity
            t_l.append(t)
            eh.append(float(np.hypot(e[0], e[1])))
            hpl.append(ig.get("hpl") or np.nan)
            omj.append((ig["test"] / ig["threshold"]) if ig.get("test") is not None and ig.get("threshold") else np.nan)
            iskl.append(bool(meta is not None and meta.sat_id in (ig.get("excluded") or [])))
        out[ime] = dict(t=np.array(t_l), eh=np.array(eh), hpl=np.array(hpl), omj=np.array(omj), iskl=np.array(iskl), sat=meta.sat_id)
    r, n = out["raim"], out["bez"]
    prvo = r["t"][np.argmax(r["iskl"])] if r["iskl"].any() else None
    fig, axs = plt.subplots(2, 1, figsize=(6.4, 4.2), sharex=True)
    axs[0].plot(n["t"], n["eh"], color=NARANCASTA, label="bez RAIM-a")
    axs[0].plot(r["t"], r["eh"], color=PLAVA, label="s RAIM-om (FDE)")
    axs[0].plot(r["t"], r["hpl"], color=ZELENA, lw=1, ls="--", label="HPL")
    axs[0].axvline(120, color=SIVA, lw=0.8, ls=":")
    if prvo is not None:
        axs[0].axvline(prvo, color=CRVENA, lw=0.8, ls=":")
    axs[0].set_ylabel("horizontalno [m]")
    axs[0].set_yscale("log")
    axs[0].legend(loc="upper left", fontsize=7.5)
    axs[1].plot(r["t"], r["omj"], color=PLAVA, lw=1, label="T/T_d (prijemnik s RAIM-om)")
    if prvo is not None:
        axs[1].axvline(prvo, color=CRVENA, lw=0.8, ls=":")
    axs[1].axhline(1, color="black", lw=0.8, ls="--")
    axs[1].set_yscale("log")
    axs[1].set_ylabel("T / T_d")
    axs[1].set_xlabel("vrijeme [s]  (kvar raste 0,5 m/s od t = 120 s)")
    axs[1].legend(loc="upper left", fontsize=7.5)
    spremi(fig, "10-rampa")
    b["rampa"] = dict(sat=r["sat"], prvo_iskljucenje_s=None if prvo is None else int(prvo),
                      kvar_pri_iskljucenju_m=None if prvo is None else round(0.5 * (prvo - 120), 1),
                      eh_prije_iskljucenja=round(float(r["eh"][r["t"] == prvo - 1][0]), 1) if prvo is not None else None,
                      omjer_max_prije=round(float(np.nanmax(r["omj"][(r["t"] >= 120) & (r["t"] < prvo)])), 2) if prvo else None,
                      omjer_pri_iskljucenju=round(float(r["omj"][r["t"] == prvo][0]), 2) if prvo is not None else None,
                      bez_eh_kraj=round(float(np.median(n["eh"][-30:])), 1), raim_eh_kraj=round(float(np.median(r["eh"][-30:])), 1),
                      kvar_kraj_m=round(0.5 * (419 - 120), 1))


def roc(b):
    r = ucitaj_studiju("raim_roc")
    if r is None:
        return
    met = ("raim_pd", "h_err_p95", "false_alarm_rate", "correct_exclusion_rate")
    out = {}
    for pfa in (1e-2, 1e-4, 1e-7):
        niz = agregat(r, met, "attack.bias_m", filtar=lambda p, pfa=pfa: abs(p["raim.pfa"] - pfa) < pfa * 1e-6)
        out[f"{pfa:g}"] = [dict(x=p["x"], **{m: (None if p[m]["mean"] is None else round(p[m]["mean"], 3)) for m in met}) for p in niz]
    b["roc"] = out
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    for (k, niz), boja in zip(out.items(), (PLAVA, ZELENA, LJUBICASTA)):
        oznaka = {"0.01": "10⁻²", "0.0001": "10⁻⁴", "1e-07": "10⁻⁷"}[k]
        ax.plot([p["x"] for p in niz], [np.nan if p["raim_pd"] is None else p["raim_pd"] for p in niz], "o-", ms=3.5, color=boja,
                label=f"P_FA = {oznaka}")
    ax.set_xlabel("kvar sata jednog satelita [m]")
    ax.set_ylabel("vjerojatnost detekcije po epohi")
    ax.set_ylim(-0.02, 1.02)
    ax.legend()
    decimalni_zarez(ax)
    spremi(fig, "10-roc")


def main():
    b = {"pfa": raim.RAIM_PFA, "pmd": raim.RAIM_PMD, "hal": raim.RAIM_HAL}
    razdiobe(b)
    kalibracija(b)
    rampa(b)
    roc(b)
    with open(os.path.join(UDZBENIK, "skripte", "brojke_10.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps(b, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
