"""Poglavlje 12 — napadi: četiri napada kroz vrijeme, studije koordiniranog spoofa i ometanja."""
import json
import os

import numpy as np

from stil import CRVENA, LJUBICASTA, NARANCASTA, PLAVA, SIVA, SUSTAVI, UDZBENIK, ZELENA, agregat, decimalni_zarez, plt, spremi, ucitaj_studiju

import spoofing as sp

LAT, LON, ALT = 45.815, 15.982, 120.0
NAPADI = [
    ("koordinirani spoof (600 m prema istoku)", sp.CoordinatedSpoof(offset_e=600.0, start=60, end=180)),
    ("naivni spoof (2 satelita × 5 km)", sp.NaiveMultiSpoof(n=2, bias_m=5000.0, start=60, end=180)),
    ("meaconing (svi signali +4 km)", sp.Meaconing(delay_m=4000.0, start=60, end=180)),
    ("ometanje (J/N do 20 dB)", sp.Jamming(js_db=20.0, start=60, end=180)),
]


def vremenski(b):
    fig, axs = plt.subplots(2, 2, figsize=(6.8, 4.6), sharex=True)
    out = {}
    for ax, (ime, napad) in zip(axs.flat, NAPADI):
        d = sp.run_attack(LAT, LON, ALT, napad, seconds=300, seed=1234)
        t = np.array([x[0] for x in d["errors"]])
        e = np.array([x[1] for x in d["errors"]])
        ax.axvspan(60, 300, color=CRVENA, alpha=0.06, linewidth=0)
        ax.plot(t, e, color=PLAVA, lw=1.1, label="pogreška")
        if d["alarms"]:
            ta = [a[0] for a in d["alarms"]]
            ax.plot(ta, np.interp(ta, t, e), "x", color=CRVENA, ms=4, label="RAIM")
        if d["target_err"]:
            tt = [x[0] for x in d["target_err"]]
            ax.plot(tt, [x[1] for x in d["target_err"]], color=NARANCASTA, lw=1, ls="--", label="udaljenost od cilja")
        if d["fix_lost"]:
            ax.plot(d["fix_lost"], np.full(len(d["fix_lost"]), 0.6), "|", color="black", ms=6, label="nema fixa")
        ax2 = ax.twinx()
        ax2.step(d["times"], d["tracked"], where="mid", color=SIVA, lw=0.7, alpha=0.8)
        ax2.set_ylim(0, 14)
        ax2.grid(False)
        ax2.tick_params(labelsize=7, colors=SIVA)
        ax.set_yscale("log")
        ax.set_ylim(0.5, 2e4)
        ax.set_title(ime, fontsize=8)
        ax.legend(fontsize=6.5, loc="upper left")
        u_prozoru = e[(t >= 200) & (t < 300)]
        out[napad.name] = dict(
            pogreska_kraj=round(float(np.median(u_prozoru)), 1) if len(u_prozoru) else None,
            alarmi=len(d["alarms"]), bez_fixa=len(d["fix_lost"]),
            sateliti_min=int(np.min(d["tracked"])), sateliti_prije=int(np.median(d["tracked"][:60])),
            cilj_kraj=round(float(np.median([x[1] for x in d["target_err"] if x[0] >= 200])), 1) if d["target_err"] else None,
            prvi_alarm=(int(d["alarms"][0][0]) if d["alarms"] else None))
    for ax in axs[1]:
        ax.set_xlabel("vrijeme [s] (napad od 60 s)")
    for ax in axs[:, 0]:
        ax.set_ylabel("[m]")
    spremi(fig, "12-napadi")
    b["vremenski"] = out


def studije(b):
    s = ucitaj_studiju("spoof_offset")
    j = ucitaj_studiju("jamming_jn")
    if s is None or j is None:
        return
    ms = ("final_err", "mi_rate", "hmi_events", "hpl_median", "raim_detections", "integrity_availability")
    b["spoof"] = [dict(x=p["x"], **{m: None if p[m]["mean"] is None else round(p[m]["mean"], 3) for m in ms})
                  for p in agregat(s, ms, "attack.offset_e")]
    mj = ("win_availability", "h_err_p95", "integrity_availability", "n_sats_mean", "hpl_median")
    b["jam"] = {}
    for sk, ime in ((("GPS",), "GPS"), (("GPS", "GAL", "GLO", "BDS"), "četiri sustava")):
        b["jam"][ime] = [dict(x=p["x"], **{m: None if p[m]["mean"] is None else round(p[m]["mean"], 3) for m in mj})
                         for p in agregat(j, mj, "attack.js_db", filtar=lambda par, sk=sk: tuple(par["systems"]) == sk)]
    fig, axs = plt.subplots(1, 2, figsize=(6.8, 2.8))
    x = [p["x"] for p in b["spoof"]]
    axs[0].plot(x, [100 * p["mi_rate"] for p in b["spoof"]], "o-", color=CRVENA, ms=3.5, label="lažna informacija [% epoha]")
    axs[0].plot(x, [p["raim_detections"] for p in b["spoof"]], "s-", color=PLAVA, ms=3.5, label="RAIM detekcije")
    axs[0].set_xlabel("pomak cilja koordiniranog spoofa [m]")
    axs[0].set_title("koordinirani spoof", fontsize=8.5)
    axs[0].legend(fontsize=7)
    for ime, boja in (("GPS", SUSTAVI["GPS"]), ("četiri sustava", "black")):
        niz = b["jam"][ime]
        axs[1].plot([p["x"] for p in niz], [100 * p["win_availability"] for p in niz], "o-", ms=3.5, color=boja, label=ime)
    axs[1].set_xlabel("J/N ometača [dB]")
    axs[1].set_ylabel("epohe s fixom za napada [%]")
    axs[1].set_title("ometanje", fontsize=8.5)
    axs[1].legend(fontsize=7)
    for ax in axs:
        decimalni_zarez(ax)
    spremi(fig, "12-studije")


def main():
    b = {}
    vremenski(b)
    studije(b)
    with open(os.path.join(UDZBENIK, "skripte", "brojke_12.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, ensure_ascii=False)
    print(json.dumps(b, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
