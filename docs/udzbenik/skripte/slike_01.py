"""Poglavlje 1 — koliko se satelita vidi: idealizirane (Walker) i prave orbite (CelesTrak snimka)."""
import json
import os
import tempfile

import numpy as np

from stil import SUSTAVI, SIVA, UDZBENIK, plt, spremi

os.environ["GPSWEB_CACHE"] = tempfile.mkdtemp()      # nikad mreža: ugrađena snimka elemenata

import real_orbits                                   # noqa: E402
from physics_engine import C, R_EARTH                # noqa: E402
from realdata import az_el                           # noqa: E402
from satellite import GNSS_SYSTEMS, MultiGNSSConstellation, WalkerDeltaConstellation  # noqa: E402
from utils import lla_to_ecef                        # noqa: E402

LAT, LON, ALT = 45.815, 15.982, 120.0
MASKA = 10.0
EPOHA = "2026-11-20T00:00:00Z"
KORAK = 300.0


def vidljivi(sateliti, rx, sustavi=None):
    n = 0
    for s in sateliti:
        if sustavi and s.system not in sustavi:
            continue
        if np.degrees(az_el(rx, s.current_pos)[1]) >= MASKA:
            n += 1
    return n


def main():
    rx = np.array(lla_to_ecef(LAT, LON, ALT))
    t = np.arange(0.0, 86400.0 + 1, KORAK)
    walker_gps = WalkerDeltaConstellation(rng=np.random.default_rng(0))
    walker_svi = MultiGNSSConstellation(rng=np.random.default_rng(0))
    gp = real_orbits.load_gp(allow_fetch=False)
    prave = real_orbits.RealConstellation(EPOHA, rng=np.random.default_rng(0), gp=gp)
    nizovi = {k: [] for k in ("w_gps", "w_svi", "p_gps", "p_svi")}
    for tt in t:
        walker_gps.update_all(tt)
        walker_svi.update_all(tt)
        prave.update_all(tt)
        nizovi["w_gps"].append(vidljivi(walker_gps.satellites, rx))
        nizovi["w_svi"].append(vidljivi(walker_svi.satellites, rx))
        nizovi["p_gps"].append(vidljivi(prave.satellites, rx, {"GPS"}))
        nizovi["p_svi"].append(vidljivi(prave.satellites, rx))
    nizovi = {k: np.array(v) for k, v in nizovi.items()}

    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    h = t / 3600.0
    ax.plot(h, nizovi["p_svi"], color="black", lw=1.3, label="prave orbite, četiri sustava")
    ax.plot(h, nizovi["w_svi"], color=SIVA, lw=1.1, ls="--", label="Walker, četiri sustava (96)")
    ax.plot(h, nizovi["p_gps"], color=SUSTAVI["GPS"], lw=1.4, label="prave orbite, GPS")
    ax.plot(h, nizovi["w_gps"], color=SUSTAVI["GPS"], lw=1.1, ls="--", label="Walker, GPS (24)")
    ax.set_xlabel("vrijeme od 20. 11. 2026. 00:00 UTC [h]")
    ax.set_ylabel(f"vidljivi sateliti (elevacija ≥ {MASKA:.0f}°)")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_ylim(0, None)
    ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.22))
    spremi(fig, "01-vidljivi-sateliti")

    # geometrija signala: udaljenost i vrijeme leta GPS signala u zenitu i na 5°
    rs = R_EARTH + GNSS_SYSTEMS["GPS"]["alt"]

    def kosa(el_deg):
        e = np.radians(el_deg)
        return float(np.sqrt(rs ** 2 - (R_EARTH * np.cos(e)) ** 2) - R_EARTH * np.sin(e))

    brojke = {
        "snimka_po_sustavu": {s: sum(1 for x in prave.satellites if x.system == s) for s in ("GPS", "GAL", "GLO", "BDS")},
        "snimka_ukupno": len(prave.satellites),
        "maska_deg": MASKA,
        "vid": {k: dict(min=int(v.min()), max=int(v.max()), sred=round(float(v.mean()), 1)) for k, v in nizovi.items()},
        "d_zenit_km": round(kosa(90) / 1e3, 0), "d_5_km": round(kosa(5) / 1e3, 0),
        "tau_zenit_ms": round(kosa(90) / C * 1e3, 1), "tau_5_ms": round(kosa(5) / C * 1e3, 1),
        "m_po_ns": round(C * 1e-9, 3),
    }
    with open(os.path.join(UDZBENIK, "skripte", "brojke_01.json"), "w", encoding="utf-8") as f:
        json.dump(brojke, f, indent=1, ensure_ascii=False)
    print(json.dumps(brojke, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
