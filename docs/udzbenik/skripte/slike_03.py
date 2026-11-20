"""Poglavlje 3 — orbite: skyplot kroz dan (rupa na sjeveru), tragovi po Zemlji, fazni raspored Walkera."""
import json
import os
import tempfile

import numpy as np

from stil import CRVENA, PLAVA, SIVA, SUSTAVI, UDZBENIK, plt, spremi

os.environ["GPSWEB_CACHE"] = tempfile.mkdtemp()

import real_orbits                                                    # noqa: E402
from physics_engine import J2, MU, R_EARTH, R_EQ_J2, get_orbital_period  # noqa: E402
from realdata import az_el                                            # noqa: E402
from satellite import GNSS_SYSTEMS, WalkerDeltaConstellation           # noqa: E402
from utils import ecef_to_lla, lla_to_ecef                            # noqa: E402

EPOHA = "2026-11-20T00:00:00Z"
ZVJEZDANI_DAN = 86164.0905
MJESTA = [("Zagreb, 45,8° N", 45.815, 15.982), ("Quito, 0,2° J", -0.18, -78.47), ("Longyearbyen, 78,2° N", 78.22, 15.65)]


def skyplot():
    gp = real_orbits.load_gp(allow_fetch=False)
    con = real_orbits.RealConstellation(EPOHA, gp=gp, systems=("GPS",))
    t = np.arange(0.0, 86400.0, 120.0)
    fig, axs = plt.subplots(1, 3, figsize=(7.0, 2.9), subplot_kw={"projection": "polar"})
    brojke = {}
    for ax, (ime, la, lo) in zip(axs, MJESTA):
        rx = np.array(lla_to_ecef(la, lo, 0.0))
        tragovi = {s.sat_id: ([], []) for s in con.satellites}
        sjever = 0
        ukupno = 0
        for tt in t:
            con.update_all(tt)
            for s in con.satellites:
                a, e = az_el(rx, s.current_pos)
                if e > 0:
                    tragovi[s.sat_id][0].append(a)
                    tragovi[s.sat_id][1].append(90 - np.degrees(e))
                    if np.degrees(e) >= 10:
                        ukupno += 1
                        if abs(((np.degrees(a) + 180) % 360) - 180) < 30:
                            sjever += 1
                else:
                    tragovi[s.sat_id][0].append(np.nan)
                    tragovi[s.sat_id][1].append(np.nan)
        for az, zen in tragovi.values():
            ax.plot(az, zen, color=SUSTAVI["GPS"], lw=0.5, alpha=0.8)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_ylim(0, 90)
        ax.set_yticks([30, 60])
        ax.set_yticklabels(["60°", "30°"], fontsize=6)
        ax.set_rlabel_position(135)
        ax.set_xticks(np.radians([0, 90, 180, 270]))
        ax.set_xticklabels(["S", "I", "J", "Z"], fontsize=7)
        ax.set_title(ime, fontsize=8.5, pad=12)
        brojke[ime.split(",")[0]] = round(100.0 * sjever / max(ukupno, 1), 1)
    spremi(fig, "03-skyplot-gps")
    return brojke


def tragovi_po_zemlji():
    gp = real_orbits.load_gp(allow_fetch=False)
    con = real_orbits.RealConstellation(EPOHA, gp=gp)
    po_id = {s.sat_id: s for s in con.satellites}
    odabir = []
    for sustav in ("GPS", "GAL", "GLO"):
        odabir.append(next(s for s in con.satellites if s.system == sustav))
    for oznaka in ("C04", "C06", "C20"):            # GEO, IGSO, MEO (BeiDou)
        if oznaka in po_id:
            odabir.append(po_id[oznaka])
    t = np.arange(0.0, 86400.0 + 1, 180.0)
    fig, ax = plt.subplots(figsize=(6.6, 3.3))
    for s in odabir:
        lat, lon = [], []
        for tt in t:
            s.update_position(tt)
            la, lo, _ = ecef_to_lla(*s.current_pos)
            lat.append(la)
            lon.append(lo)
        lon = np.array(lon)
        lat = np.array(lat)
        skok = np.where(np.abs(np.diff(lon)) > 180)[0] + 1
        lon = np.insert(lon, skok, np.nan)
        lat = np.insert(lat, skok, np.nan)
        boja = SUSTAVI[s.system]
        stil = "-" if s.system != "BDS" else {"C04": "o", "C06": "--", "C20": ":"}.get(s.sat_id, "-")
        if stil == "o":
            ax.plot(lon[0], lat[0], "o", color=boja, ms=6, label=f"{s.sat_id} (BeiDou GEO)")
        else:
            opis = {"GPS": "GPS", "GAL": "Galileo", "GLO": "GLONASS"}.get(s.system)
            opis = opis or ("BeiDou IGSO" if s.sat_id == "C06" else "BeiDou MEO")
            ax.plot(lon, lat, stil, color=boja, lw=1.1, label=f"{s.sat_id} ({opis})")
    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.set_xticks(range(-180, 181, 60))
    ax.set_yticks(range(-90, 91, 30))
    ax.set_xlabel("geografska dužina [°]")
    ax.set_ylabel("geografska širina [°]")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.18), fontsize=7)
    spremi(fig, "03-tragovi")


def walker_faze():
    """Argument širine 4 satelita prve ravnine: stari bug (m0 kao radijani) i ispravno."""
    con = WalkerDeltaConstellation(rng=np.random.default_rng(0))
    ravnina = [s for s in con.satellites if s.sat_id.startswith("SAT_0_")]
    fig, axs = plt.subplots(1, 2, figsize=(5.2, 2.7), subplot_kw={"projection": "polar"})
    for ax, naslov, fn in ((axs[0], "prije ispravka (M₀ kao radijani)", lambda m: m % (2 * np.pi)),
                           (axs[1], "ispravno (M₀ u stupnjevima)", np.radians)):
        kut = [fn(s.m0) for s in ravnina]
        ax.plot(np.linspace(0, 2 * np.pi, 200), np.ones(200), color=SIVA, lw=0.8)
        ax.plot(kut, np.ones(len(kut)), "o", color=CRVENA if "prije" in naslov else PLAVA, ms=8)
        for k, s in zip(kut, ravnina):
            ax.annotate(s.sat_id[-1], (k, 1.0), xytext=(k, 1.25), ha="center", va="center", fontsize=7)
        ax.set_ylim(0, 1.4)
        ax.set_yticks([])
        ax.set_xticks(np.radians(range(0, 360, 90)))
        ax.set_title(naslov, fontsize=8.5, pad=10)
    spremi(fig, "03-walker-faze")


def main():
    brojke = {"sjever_udio_posto": skyplot()}
    tragovi_po_zemlji()
    walker_faze()
    for k, cfg in GNSS_SYSTEMS.items():
        a = R_EARTH + cfg["alt"]
        n = np.sqrt(MU / a ** 3)
        T = get_orbital_period(a)
        i = np.radians(cfg["inc"])
        lan_dot = -1.5 * n * J2 * (R_EQ_J2 / a) ** 2 * np.cos(i)
        w_dot = 0.75 * n * J2 * (R_EQ_J2 / a) ** 2 * (4 - 5 * np.sin(i) ** 2)
        brojke[k] = dict(a_km=round(a / 1e3, 0), T_h=round(T / 3600, 3), T_min=round(T / 60, 1),
                         ophoda_po_zv_danu=round(ZVJEZDANI_DAN / T, 3),
                         lan_dot_deg_dan=round(float(np.degrees(lan_dot) * 86400), 4),
                         w_dot_deg_dan=round(float(np.degrees(w_dot) * 86400), 4),
                         v_kms=round(float(np.sqrt(MU / a)) / 1e3, 2))
    # Keplerova jednadžba za vježbu: M = 1 rad, e = 0,015
    M, e = 1.0, 0.015
    E = M
    koraci = [E]
    for _ in range(4):
        E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
        koraci.append(E)
    brojke["kepler_koraci"] = [round(float(x), 10) for x in koraci]
    geo_a = (MU * (ZVJEZDANI_DAN / (2 * np.pi)) ** 2) ** (1 / 3)
    brojke["geo_visina_km_sfera"] = round((geo_a - R_EARTH) / 1e3, 0)
    with open(os.path.join(UDZBENIK, "skripte", "brojke_03.json"), "w", encoding="utf-8") as f:
        json.dump(brojke, f, indent=1, ensure_ascii=False)
    print(json.dumps(brojke, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
