"""Skyplot + vremenski grafovi (GDOP, greška, NIS) za zadani scenarij.

Pokreće simulaciju headless (bez 3D prikaza) i sprema PNG:
  - polarni skyplot: staze satelita po nebu (azimut/elevacija), s markerima
    trenutnog položaja i oznakom koji se prate;
  - GDOP, pogreška pozicioniranja i NIS/dof kroz vrijeme.

Za analizu geometrije konstelacije i performansi filtra bez GPU-a.

Primjer:
    python skyplot.py --lat 45.815 --lon 15.982 --seconds 300 --out skyplot.png
"""
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless renderiranje u datoteku
import matplotlib.pyplot as plt

from satellite import WalkerDeltaConstellation
from receiver import Receiver
from utils import lla_to_ecef, ecef_to_lla

# Paleta usklađena s 3D prikazom
BG, PANEL, GRID = "#0e1116", "#161b24", "#2a3547"
CYAN, GREEN, AMBER, RED, TEXT, DIM = "#22d3ee", "#34d399", "#fbbf24", "#f87171", "#e5e7eb", "#8b97a8"


def enu_azel(P, S):
    """Elevacija i azimut satelita S [ECEF] gledano iz P [ECEF]."""
    lat, lon, _ = ecef_to_lla(P[0], P[1], P[2])
    la, lo = np.radians(lat), np.radians(lon)
    sl, cl, so, co = np.sin(la), np.cos(la), np.sin(lo), np.cos(lo)
    east = np.array([-so, co, 0.0])
    north = np.array([-sl * co, -sl * so, cl])
    up = np.array([cl * co, cl * so, sl])
    d = np.asarray(S) - np.asarray(P)
    rng = np.linalg.norm(d)
    if rng == 0:
        return None
    el = np.degrees(np.arcsin(np.dot(d, up) / rng))
    az = np.degrees(np.arctan2(np.dot(d, east), np.dot(d, north))) % 360.0
    return el, az


def run(lat, lon, alt, seconds, seed):
    rng = np.random.default_rng(seed)
    con = WalkerDeltaConstellation(rng=rng)
    P = np.array(lla_to_ecef(lat, lon, alt))
    rx = Receiver(P, rng=rng)

    times, gdops, errors, nis = [], [], [], []
    tracks = {}                 # sat_id -> ([el...], [az...]) dok je iznad horizonta
    final = []                  # (el, az, sat_id, tracked) u zadnjem epohu

    for t in range(seconds):
        con.update_all(float(t))
        sigs = rx.receive_signals(con, float(t))
        pos, gdop = rx.solve_position()
        tracked_ids = {s["sat_id"] for s in sigs}

        for sat in con.satellites:
            azel = enu_azel(P, sat.current_pos)
            if azel is None or azel[0] < 0:
                continue
            el, az = azel
            tracks.setdefault(sat.sat_id, ([], []))
            tracks[sat.sat_id][0].append(el)
            tracks[sat.sat_id][1].append(az)
            if t == seconds - 1:
                final.append((el, az, sat.sat_id, sat.sat_id in tracked_ids))

        times.append(t)
        gdops.append(gdop if gdop is not None else np.nan)
        if pos is not None:
            errors.append(float(np.linalg.norm(pos - P)))
            nis.append(rx.nis / rx.nis_dof if rx.nis_dof else np.nan)
        else:
            errors.append(np.nan)
            nis.append(np.nan)

    return dict(times=np.array(times), gdops=np.array(gdops), errors=np.array(errors),
                nis=np.array(nis), tracks=tracks, final=final)


def _style_ax(ax, title):
    ax.set_facecolor(PANEL)
    ax.set_title(title, color=TEXT, fontsize=10, loc="left", fontfamily="monospace")
    ax.tick_params(colors=DIM, labelsize=8)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.grid(True, color=GRID, lw=0.5, alpha=0.6)


def plot(data, out, lat, lon):
    fig = plt.figure(figsize=(14, 7.2), facecolor=BG)
    gs = fig.add_gridspec(3, 2, width_ratios=[1.15, 1.0], hspace=0.6, wspace=0.2,
                          left=0.04, right=0.97, top=0.85, bottom=0.08)

    # --- Skyplot (polarno) ---
    axp = fig.add_subplot(gs[:, 0], projection="polar")
    axp.set_facecolor(PANEL)
    axp.set_theta_zero_location("N")
    axp.set_theta_direction(-1)          # azimut raste u smjeru kazaljke (N-E-S-W)
    axp.set_rlim(0, 90)                   # r = 90 - elevacija: centar = zenit, rub = horizont
    axp.set_rgrids([0, 30, 60, 90], labels=["90°", "60°", "30°", "0°"], color=DIM, fontsize=7)
    axp.set_thetagrids(range(0, 360, 45), labels=["N", "NE", "E", "SE", "S", "SW", "W", "NW"], color=DIM)
    axp.tick_params(colors=DIM)
    axp.spines["polar"].set_color(GRID)
    axp.grid(color=GRID, lw=0.5, alpha=0.7)

    for sid, (els, azs) in data["tracks"].items():
        r = 90 - np.array(els)
        th = np.radians(np.array(azs))
        axp.plot(th, r, color="#3a4a63", lw=0.6, alpha=0.5)

    for el, az, sid, tracked in data["final"]:
        th, r = np.radians(az), 90 - el
        axp.scatter(th, r, s=90 if tracked else 55,
                    c=GREEN if tracked else DIM, edgecolors=BG, linewidths=1.0, zorder=5)
        axp.annotate(sid.replace("SAT_", ""), (th, r), color=TEXT if tracked else DIM,
                     fontsize=6.5, ha="center", va="center", zorder=6)

    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=GREEN, markersize=8, label="praćen (u rješenju)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=DIM, markersize=7, label="vidljiv, nekorišten"),
    ]
    axp.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.11), ncol=2,
               frameon=False, labelcolor=TEXT, fontsize=8)

    # --- Vremenski grafovi ---
    tv = data["times"]
    ax1 = fig.add_subplot(gs[0, 1]); _style_ax(ax1, "GDOP")
    ax1.plot(tv, data["gdops"], color=CYAN, lw=1.3)
    ax1.axhline(6, color=AMBER, lw=0.8, ls="--", alpha=0.6)
    ax1.set_ylim(0, min(15, np.nanmax(np.append(data["gdops"], 8)) * 1.15))

    ax2 = fig.add_subplot(gs[1, 1]); _style_ax(ax2, "POGREŠKA POZICIJE [m]")
    ax2.plot(tv, data["errors"], color=GREEN, lw=1.3)
    med = np.nanmedian(data["errors"])
    ax2.axhline(med, color=AMBER, lw=0.8, ls="--", alpha=0.7)
    ax2.annotate(f"median {med:.0f} m", (tv[-1], med), color=AMBER, fontsize=7,
                 ha="right", va="bottom")

    ax3 = fig.add_subplot(gs[2, 1]); _style_ax(ax3, "NIS/dof  (konzistentnost, ~1)")
    ax3.plot(tv, data["nis"], color=RED, lw=1.1)
    ax3.axhline(1.0, color=DIM, lw=0.8, ls="--", alpha=0.7)
    ax3.set_ylim(0, 3)
    ax3.set_xlabel("epoch [s]", color=DIM, fontsize=8)

    fig.suptitle(f"GPS SIMULATOR 3D   ·   SKYPLOT & PERFORMANSE   ·   Lat {lat:.3f}  Lon {lon:.3f}",
                 color=TEXT, fontsize=13, fontfamily="monospace", x=0.04, ha="left", y=0.955)
    fig.savefig(out, dpi=110, facecolor=BG)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description="Skyplot i vremenski grafovi (headless).")
    p.add_argument("--lat", type=float, default=45.815)
    p.add_argument("--lon", type=float, default=15.982)
    p.add_argument("--alt", type=float, default=120.0)
    p.add_argument("--seconds", type=int, default=300)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--out", default="skyplot.png")
    args = p.parse_args()

    data = run(args.lat, args.lon, args.alt, args.seconds, args.seed)
    plot(data, args.out, args.lat, args.lon)
    n_tracked = sum(1 for *_, tr in data["final"] if tr)
    print(f"Spremljeno: {args.out}")
    print(f"  epoch-eva: {args.seconds}  |  satelita iznad horizonta (zadnji epoch): {len(data['final'])}"
          f"  |  praćeno: {n_tracked}")
    print(f"  GDOP median: {np.nanmedian(data['gdops']):.2f}  |  pogreška median: {np.nanmedian(data['errors']):.1f} m"
          f"  |  NIS/dof median: {np.nanmedian(data['nis']):.2f}")


if __name__ == "__main__":
    main()
