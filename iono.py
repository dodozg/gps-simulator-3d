"""Ionosferska analiza — Klobuchar model ovisan o dobu dana (#7).

Ionosferski sadržaj elektrona (TEC) mijenja se s dobom dana: raste nakon izlaska
Sunca, vrhunac je oko 14:00 lokalno, a noću pada na tanki pod. Klobuchar model
(pravi GPS algoritam, `physics_engine.klobuchar_delay`) to reproducira. Ovaj alat
crta dnevnu krivulju i ovisnost o elevaciji te kvantificira zašto dvofrekvencijski
prijemnik (iono-free L1/L2) uklanja to kašnjenje, a jednofrekvencijski ne.

Pokretanje:
    python iono.py                 # ispis + iono.png
    python iono.py --lat 45.8 --lon 16 --no-plot
"""
import argparse
import numpy as np

from physics_engine import klobuchar_delay, C, F_L1

F_L2 = 1227.60e6


def zenith_delay_m(lat, lon, tow_s, freq=F_L1):
    """Zenitno (elev=90°) Klobuchar kašnjenje u metrima za danu frekvenciju."""
    sec = klobuchar_delay(lat, lon, np.pi / 2, 0.0, tow_s)
    return C * sec * (F_L1 / freq) ** 2


def slant_delay_m(lat, lon, elev_rad, az_rad, tow_s, freq=F_L1):
    sec = klobuchar_delay(lat, lon, elev_rad, az_rad, tow_s)
    return C * sec * (F_L1 / freq) ** 2


def iono_free_residual_m(lat, lon, elev_rad, az_rad, tow_s):
    """Rezidual iono-free kombinacije: (f1²·I1 − f2²·I2)/(f1²−f2²). ~0 jer I∝1/f²."""
    i1 = slant_delay_m(lat, lon, elev_rad, az_rad, tow_s, F_L1)
    i2 = slant_delay_m(lat, lon, elev_rad, az_rad, tow_s, F_L2)
    f1, f2 = F_L1**2, F_L2**2
    return (f1 * i1 - f2 * i2) / (f1 - f2)


def diurnal(lat, lon, n=145):
    """Vrati (sati_lokalno, zenitno_kašnjenje_m) kroz 24 h."""
    tows = np.linspace(0.0, 86400.0, n)
    delays = np.array([zenith_delay_m(lat, lon, t) for t in tows])
    local_h = ((43200.0 * (lon / 180.0) + tows) % 86400.0) / 3600.0
    order = np.argsort(local_h)
    return local_h[order], delays[order]


def run(lat, lon):
    hours, dz = diurnal(lat, lon)
    peak_i = int(np.argmax(dz))
    night_mask = (hours < 4) | (hours > 22)
    night = float(np.min(dz))
    # slant vs elevacija u lokalno podne (najjača iono)
    tow_noon = (50400.0 - 43200.0 * (lon / 180.0)) % 86400.0
    elevs = np.radians(np.array([5, 10, 20, 40, 60, 90], float))
    slant = np.array([slant_delay_m(lat, lon, e, 0.0, tow_noon) for e in elevs])
    resid = abs(iono_free_residual_m(lat, lon, np.radians(20), 0.0, tow_noon))
    return dict(hours=hours, dz=dz, peak=(hours[peak_i], dz[peak_i]),
                night=night, elevs=np.degrees(elevs), slant=slant,
                if_residual=resid, l1_at20=slant_delay_m(lat, lon, np.radians(20), 0.0, tow_noon))


def report(d, lat, lon):
    print(f"Klobuchar ionosfera @ LLA({lat}, {lon})")
    print("-" * 52)
    print(f"Zenitno kašnjenje, vrh (~14 h): {d['peak'][1]:6.2f} m  (u {d['peak'][0]:4.1f} h)")
    print(f"Zenitno kašnjenje, noćni pod:   {d['night']:6.2f} m")
    print(f"Dnevni raspon (vrh/pod):        {d['peak'][1]/max(d['night'],1e-6):6.1f}x")
    print("-" * 52)
    print("Koso kašnjenje u lokalno podne po elevaciji:")
    for e, s in zip(d['elevs'], d['slant']):
        print(f"   {e:5.0f}°  {s:6.2f} m")
    print("-" * 52)
    print(f"L1-only kašnjenje (20°, podne):     {d['l1_at20']:6.2f} m  (jednofrekv. nosi punu grešku)")
    print(f"Iono-free rezidual (L1/L2):         {d['if_residual']:6.3f} m  (dvofrekv. poništava)")


def plot(d, out, lat, lon):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bg, fg, grid = "#0d1117", "#e6edf3", "#30363d"
    cyan, amber, green = "#39c5cf", "#e3b341", "#58d364"
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    fig.patch.set_facecolor(bg)
    for ax in (ax1, ax2):
        ax.set_facecolor(bg)
        for sp in ax.spines.values():
            sp.set_color(grid)
        ax.tick_params(colors=fg)
        ax.grid(True, color=grid, alpha=0.5, lw=0.5)

    ax1.plot(d['hours'], d['dz'], color=amber, lw=1.8)
    ax1.axvline(14, color=cyan, alpha=0.4, ls="--", lw=1)
    ax1.set_title("Dnevna krivulja (zenit, L1)", color=fg)
    ax1.set_xlabel("lokalno vrijeme [h]", color=fg)
    ax1.set_ylabel("iono kašnjenje [m]", color=fg)
    ax1.set_xlim(0, 24); ax1.set_xticks(range(0, 25, 4))

    ax2.plot(d['elevs'], d['slant'], "o-", color=green, lw=1.6)
    ax2.set_title("Koso kašnjenje vs elevacija (podne)", color=fg)
    ax2.set_xlabel("elevacija [°]", color=fg)
    ax2.set_ylabel("iono kašnjenje [m]", color=fg)

    fig.suptitle(f"Klobuchar ionosfera — LLA({lat}, {lon})", color=fg, y=1.02)
    fig.tight_layout()
    fig.savefig(out, dpi=120, facecolor=bg, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    p = argparse.ArgumentParser(description="Klobuchar ionosferska analiza (doba dana).")
    p.add_argument("--lat", type=float, default=45.815)
    p.add_argument("--lon", type=float, default=15.982)
    p.add_argument("--no-plot", action="store_true")
    args = p.parse_args()
    d = run(args.lat, args.lon)
    report(d, args.lat, args.lon)
    if not args.no_plot:
        out = plot(d, "iono.png", args.lat, args.lon)
        print(f"[graf] {out}")


if __name__ == "__main__":
    main()
