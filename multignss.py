"""Multi-GNSS pozicioniranje s procjenom inter-system biasa (#6).

Kombinira GPS + Galileo + GLONASS + BeiDou. Svaki sustav ima svoju vremensku
skalu pa unosi konstantni inter-system bias (ISB) u pseudoudaljenosti. Prijemnik
ga mora procijeniti kao DODATNO stanje uz položaj i vlastiti sat:

    nepoznanice = [x, y, z, c·bias,  ISB_GAL, ISB_GLO, ISB_BDS]

(GPS je referenca, njegov ISB je 0 i uključen u c·bias.) Rješava se težinskim
najmanjim kvadratima (Gauss-Newton). Više sustava = više satelita = bolja
geometrija (niži PDOP) i dostupnost fixa i tamo gdje GPS sam ne vidi dovoljno
satelita (npr. urbani kanjon = visoka maska elevacije).

Pokretanje:
    python multignss.py                       # usporedba + availability sweep -> multignss.png
    python multignss.py --lat 1.35 --lon 103.8 --mask 30 --no-plot
"""
import argparse
import numpy as np

from satellite import MultiGNSSConstellation
from utils import lla_to_ecef

BASE_SIGMA_M = 3.0     # osnovni šum pseudoudaljenosti (zenit)
CLOCK_BIAS_M = 30.0    # istinski sat prijemnika (zajednički svim satelitima) [m]


def _visible(con, R, mask_deg, use_systems):
    """Vrati listu (sat, S) satelita iznad maske iz dopuštenih sustava."""
    up = R / np.linalg.norm(R)
    out = []
    for sat in con.satellites:
        if sat.system not in use_systems:
            continue
        S = sat.current_pos
        v = S - R
        el = np.degrees(np.arcsin(np.clip(np.dot(up, v / np.linalg.norm(v)), -1, 1)))
        if el >= mask_deg:
            out.append((sat, S, el))
    return out


def _synth_measurements(vis, con, R, rng):
    """Sintetiziraj pseudoudaljenosti: geometrija + sat prijemnika + ISP + šum."""
    meas = []
    for sat, S, el in vis:
        rho = np.linalg.norm(S - R)
        sigma = BASE_SIGMA_M / np.sin(np.radians(max(el, 5.0)))
        pr = rho + CLOCK_BIAS_M + con.sys_bias[sat.system] + rng.normal(0, sigma)
        meas.append((sat.system, S, pr, sigma))
    return meas


def solve(meas, R_true, rng, max_iter=12):
    """Težinski GN za [x,y,z,c·bias, ISB...]. Vrati metrike ili None."""
    systems = sorted({m[0] for m in meas})
    ref = "GPS" if "GPS" in systems else systems[0]
    extra = [s for s in systems if s != ref]          # sustavi s vlastitim ISB stanjem
    col = {s: 4 + k for k, s in enumerate(extra)}      # stupac ISB-a po sustavu
    nx = 4 + len(extra)
    if len(meas) < nx:
        return None                                     # premalo mjerenja za sve nepoznanice

    x = np.zeros(nx)
    x[:3] = R_true + rng.normal(0, 30000.0, 3)         # gruba a-priori (~30 km)

    for _ in range(max_iter):
        H, r, w = [], [], []
        for sysname, S, pr, sigma in meas:
            d = x[:3] - S
            rho = np.linalg.norm(d)
            if rho < 1.0:
                rho = 1.0
            row = np.zeros(nx)
            row[:3] = d / rho
            row[3] = 1.0
            if sysname in col:
                row[col[sysname]] = 1.0
            pred = rho + x[3] + (x[col[sysname]] if sysname in col else 0.0)
            H.append(row); r.append(pr - pred); w.append(1.0 / sigma**2)
        H = np.array(H); r = np.array(r); W = np.diag(w)
        try:
            N = H.T @ W @ H
            dx = np.linalg.solve(N, H.T @ W @ r)
        except np.linalg.LinAlgError:
            return None
        x = x + dx
        if np.linalg.norm(dx[:3]) < 1e-3:
            break

    # PDOP (nevagani) iz geometrije položaja
    try:
        cov = np.linalg.inv(H.T @ H)
        pdop = float(np.sqrt(cov[0, 0] + cov[1, 1] + cov[2, 2]))
    except np.linalg.LinAlgError:
        pdop = float("inf")

    isb_est = {s: float(x[col[s]]) for s in extra}
    return dict(pos_err=float(np.linalg.norm(x[:3] - R_true)),
                pdop=pdop, n=len(meas), systems=systems,
                isb_est=isb_est, ref=ref)


def run_compare(lat, lon, alt, mask_deg=10.0, seed=1234, t0=0.0):
    """GPS-only vs svi sustavi na jednoj lokaciji + availability sweep po maski."""
    rng = np.random.default_rng(seed)
    con = MultiGNSSConstellation(rng=rng)
    con.update_all(float(t0))
    R = np.array(lla_to_ecef(lat, lon, alt))

    def _run(use_systems, mask):
        vis = _visible(con, R, mask, use_systems)
        meas = _synth_measurements(vis, con, R, np.random.default_rng(seed + 7))
        return vis, solve(meas, R, np.random.default_rng(seed + 99))

    all_sys = ("GPS", "GAL", "GLO", "BDS")
    gps_vis, gps_sol = _run(("GPS",), mask_deg)
    all_vis, all_sol = _run(all_sys, mask_deg)

    masks = np.arange(5, 46, 5)
    sweep = {"mask": masks, "gps_n": [], "all_n": [], "gps_pdop": [], "all_pdop": []}
    for mk in masks:
        gv, gs = _run(("GPS",), mk)
        av, as_ = _run(all_sys, mk)
        sweep["gps_n"].append(len(gv))
        sweep["all_n"].append(len(av))
        sweep["gps_pdop"].append(gs["pdop"] if gs else np.nan)
        sweep["all_pdop"].append(as_["pdop"] if as_ else np.nan)
    for k in ("gps_n", "all_n", "gps_pdop", "all_pdop"):
        sweep[k] = np.array(sweep[k], dtype=float)

    return dict(gps=(len(gps_vis), gps_sol), all=(len(all_vis), all_sol),
                sweep=sweep, sys_bias=con.sys_bias, mask=mask_deg)


def report(data, lat, lon):
    gps_n, gps = data["gps"]
    all_n, alls = data["all"]
    print(f"Multi-GNSS @ LLA({lat}, {lon})   maska elevacije: {data['mask']:.0f}°")
    print("=" * 56)
    print(f"{'':16s}{'GPS-only':>12s}{'GPS+GAL+GLO+BDS':>20s}")
    print(f"{'Satelita':16s}{gps_n:>12d}{all_n:>20d}")
    pg = f"{gps['pdop']:.2f}" if gps else "n/a"
    pa = f"{alls['pdop']:.2f}" if alls else "n/a"
    print(f"{'PDOP':16s}{pg:>12s}{pa:>20s}")
    eg = f"{gps['pos_err']:.1f} m" if gps else "NEMA FIXA"
    ea = f"{alls['pos_err']:.1f} m" if alls else "NEMA FIXA"
    print(f"{'Greška':16s}{eg:>12s}{ea:>20s}")
    print("-" * 56)
    print("Procjena inter-system biasa (istina -> procjena):")
    if alls:
        for s, truth in data["sys_bias"].items():
            if s in alls["isb_est"]:
                print(f"   {s}:  {truth:+7.1f} m  ->  {alls['isb_est'][s]:+7.1f} m")
    print("-" * 56)
    sw = data["sweep"]
    print("Dostupnost po maski elevacije (broj satelita):")
    print(f"   {'maska°':>7s}{'GPS':>6s}{'SVI':>6s}")
    for i, mk in enumerate(sw["mask"]):
        print(f"   {int(mk):>7d}{int(sw['gps_n'][i]):>6d}{int(sw['all_n'][i]):>6d}")


def plot(data, out, lat, lon):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bg, fg, grid = "#0d1117", "#e6edf3", "#30363d"
    cyan, amber = "#39c5cf", "#e3b341"
    sw = data["sweep"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    fig.patch.set_facecolor(bg)
    for ax in (ax1, ax2):
        ax.set_facecolor(bg)
        for sp in ax.spines.values():
            sp.set_color(grid)
        ax.tick_params(colors=fg)
        ax.grid(True, color=grid, alpha=0.5, lw=0.5)

    ax1.plot(sw["mask"], sw["gps_n"], "o-", color=cyan, label="GPS")
    ax1.plot(sw["mask"], sw["all_n"], "o-", color=amber, label="GPS+GAL+GLO+BDS")
    ax1.axhline(4, color="#f8776a", ls="--", lw=1, alpha=0.7)
    ax1.set_title("Vidljivi sateliti vs maska", color=fg)
    ax1.set_xlabel("maska elevacije [°]", color=fg)
    ax1.set_ylabel("broj satelita", color=fg)
    ax1.legend(facecolor=bg, edgecolor=grid, labelcolor=fg, fontsize=8)

    ax2.plot(sw["mask"], sw["gps_pdop"], "o-", color=cyan, label="GPS")
    ax2.plot(sw["mask"], sw["all_pdop"], "o-", color=amber, label="SVI")
    ax2.set_title("PDOP vs maska (niže = bolje)", color=fg)
    ax2.set_xlabel("maska elevacije [°]", color=fg)
    ax2.set_ylabel("PDOP", color=fg)
    ax2.set_ylim(0, min(20, np.nanmax(sw["gps_pdop"][np.isfinite(sw["gps_pdop"])]) + 2))
    ax2.legend(facecolor=bg, edgecolor=grid, labelcolor=fg, fontsize=8)

    fig.suptitle(f"Multi-GNSS — LLA({lat}, {lon})", color=fg, y=1.02)
    fig.tight_layout()
    fig.savefig(out, dpi=120, facecolor=bg, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    p = argparse.ArgumentParser(description="Multi-GNSS pozicioniranje + inter-system bias.")
    p.add_argument("--lat", type=float, default=45.815)
    p.add_argument("--lon", type=float, default=15.982)
    p.add_argument("--alt", type=float, default=120.0)
    p.add_argument("--mask", type=float, default=10.0, help="maska elevacije [°]")
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--no-plot", action="store_true")
    args = p.parse_args()

    data = run_compare(args.lat, args.lon, args.alt, args.mask, args.seed)
    report(data, args.lat, args.lon)
    if not args.no_plot:
        out = plot(data, "multignss.png", args.lat, args.lon)
        print(f"[graf] {out}")


if __name__ == "__main__":
    main()
