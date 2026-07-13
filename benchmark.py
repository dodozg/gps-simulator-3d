"""Headless pokretanje simulacije bez GUI-ja.

Vrti prijemnik na fiksnoj lokaciji kroz zadani broj epoch-eva i ispisuje
statistiku greške pozicioniranja. Koristi se za mjerenje utjecaja promjena
u engine-u (npr. EKF tuning, WGS-84 geodezija) bez pokretanja 3D prikaza.

Primjer:
    python benchmark.py --lat 45.815 --lon 15.982 --alt 120 --seconds 300
"""
import argparse
import numpy as np

from satellite import WalkerDeltaConstellation
from receiver import Receiver
from utils import lla_to_ecef


def run_scenario(lat, lon, alt, seconds, seed=None):
    """Vrati (greske, gdop-ovi, alarmi, nis) za zadani scenarij.

    Jedan np.random.Generator (sjeme = `seed`) dijele konstelacija i prijemnik,
    pa je cijela simulacija reproducibilna bez oslanjanja na globalno np.random.
    """
    rng = np.random.default_rng(seed)

    constellation = WalkerDeltaConstellation(rng=rng)
    gt = np.array(lla_to_ecef(lat, lon, alt))
    rx = Receiver(gt, rng=rng)

    errors, gdops, alarms, nis = [], [], [], []
    for t in range(seconds):
        constellation.update_all(float(t))
        rx.receive_signals(constellation, float(t))
        pos, gdop = rx.solve_position()
        if pos is not None:
            errors.append(np.linalg.norm(pos - gt))
            if gdop is not None:
                gdops.append(gdop)
            if rx.nis_dof:
                nis.append(rx.nis / rx.nis_dof)  # NIS/dof ~ 1 kad je filter konzistentan
        if rx.raim_alarm:
            alarms.append((t, rx.raim_alarm))

    return np.array(errors), np.array(gdops), alarms, np.array(nis)


def main():
    p = argparse.ArgumentParser(description="Headless GPS simulacija i statistika greške.")
    p.add_argument("--lat", type=float, default=45.815, help="Geografska širina [°]")
    p.add_argument("--lon", type=float, default=15.982, help="Geografska dužina [°]")
    p.add_argument("--alt", type=float, default=120.0, help="Visina [m]")
    p.add_argument("--seconds", type=int, default=300, help="Broj simulacijskih epoch-eva")
    p.add_argument("--seed", type=int, default=1234, help="Sjeme RNG-a (za reproducibilnost)")
    args = p.parse_args()

    errors, gdops, alarms, nis = run_scenario(
        args.lat, args.lon, args.alt, args.seconds, seed=args.seed
    )

    print(f"Lokacija:  LLA({args.lat}, {args.lon}, {args.alt})")
    print(f"Epoch-eva: {args.seconds}  |  riješeno: {len(errors)}  |  seed: {args.seed}")
    print("-" * 44)
    if len(errors) == 0:
        print("Nijedan epoch nije riješen (premalo satelita?).")
        return

    conv = errors[len(errors) // 2:]  # druga polovica = nakon konvergencije
    print(f"Cold-start greška:     {errors[0]:8.1f} m")
    print(f"Greška (median):       {np.median(errors):8.1f} m")
    print(f"Konvergirano (mean):   {conv.mean():8.1f} m")
    print(f"Konvergirano (95%):    {np.percentile(conv, 95):8.1f} m")
    print(f"Maksimalna greška:     {errors.max():8.1f} m")
    if len(gdops):
        print(f"GDOP (mean):           {gdops.mean():8.2f}")
    if len(nis):
        print(f"NIS/dof (mean):        {nis.mean():8.2f}   (konzistentno ~1)")
    print(f"RAIM alarma:           {len(alarms):8d}")
    if alarms:
        t, msg = alarms[0]
        print(f"  prvi @ t={t}s: {msg}")


if __name__ == "__main__":
    main()
