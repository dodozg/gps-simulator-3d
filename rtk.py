"""Carrier-phase RTK (Real-Time Kinematic) — cm-precizno relativno pozicioniranje.

Za razliku od kodnog rješenja (pseudoudaljenost, ~desetci metara zbog multipatha),
RTK koristi FAZU nosioca (valna duljina L1 ~19 cm, šum ~mm) i dvostruke razlike
(double differencing, DD) između rovera/baze i para satelita, čime se ponište
satni pomaci i (kod kratke baze) atmosfera. Ostaje cjelobrojna neodređenost
(integer ambiguity) koju treba razriješiti; kad se fiksira na ispravan cijeli broj,
rješenje je centimetarsko.

Ovdje je implementiran statički jedno-bazni RTK:
  1. prikupi DD faze kroz više epoha (geometrija se mijenja kako sateliti putuju),
  2. float rješenje (LS): baseline + realne DD neodređenosti,
  3. fiksiranje cijelih brojeva zaokruživanjem (u simulaciji sa mm šumom pouzdano),
  4. fiksno rješenje: baseline uz fiksne cijele brojeve -> cm.

Primjer:
    python rtk.py
"""
import argparse
import numpy as np

from satellite import WalkerDeltaConstellation
from utils import lla_to_ecef
from physics_engine import C

F_L1 = 1575.42e6
LAMBDA1 = C / F_L1          # ~0.1903 m, valna duljina L1
PHASE_SIGMA_M = 0.002       # šum faze nosioca ~2 mm
CODE_SIGMA_M = 3.0          # šum koda ~3 m (za usporedbu)


def _visible(sat_positions, rec_pos, mask_deg):
    up = rec_pos / np.linalg.norm(rec_pos)
    vis = set()
    for sid, sp in sat_positions.items():
        v = sp - rec_pos
        el = np.degrees(np.arcsin(np.dot(up, v / np.linalg.norm(v))))
        if el >= mask_deg:
            vis.add(sid)
    return vis


def rtk_solve(rover_llh, base_llh, n_epochs=40, dt_epoch=30.0, seed=0, mask_deg=15.0):
    """Riješi položaj rovera RTK-om uz poznatu bazu. Vrati metrike ili None."""
    rng = np.random.default_rng(seed)
    con = WalkerDeltaConstellation(rng=rng)
    R = np.array(lla_to_ecef(*rover_llh), dtype=float)   # prava pozicija rovera
    B = np.array(lla_to_ecef(*base_llh), dtype=float)     # baza (poznata točno)

    times = [i * dt_epoch for i in range(n_epochs)]
    sat_pos = {}
    for t in times:
        con.update_all(t)
        sat_pos[t] = {s.sat_id: s.current_pos.copy() for s in con.satellites}

    # Sateliti vidljivi iz OBA prijemnika u SVIM epohama (bez cycle-slipa).
    common = None
    for t in times:
        vis = _visible(sat_pos[t], R, mask_deg) & _visible(sat_pos[t], B, mask_deg)
        common = vis if common is None else (common & vis)
    common = sorted(common)
    if len(common) < 5:
        return None
    ref = common[0]
    others = common[1:]
    m = len(others)

    # Fiksne cjelobrojne neodređenosti po (prijemnik, sat) — konstantne kroz epohe.
    Nr = {s: int(rng.integers(-200, 200)) for s in common}
    Nb = {s: int(rng.integers(-200, 200)) for s in common}
    Ndd_true = np.array([(Nr[s] - Nb[s]) - (Nr[ref] - Nb[ref]) for s in others])

    # Mjerenja faze (u metrima) generirana JEDNOM (fiksni šum), i DD opažanja.
    DDL = {}          # t -> vektor DD faze [m] po 'others'
    DD_range_b = {}   # t -> vektor DD geometrijske udaljenosti baze [m]
    for t in times:
        sp = sat_pos[t]
        Lr = {s: np.linalg.norm(sp[s] - R) + LAMBDA1 * Nr[s] + rng.normal(0, PHASE_SIGMA_M) for s in common}
        Lb = {s: np.linalg.norm(sp[s] - B) + LAMBDA1 * Nb[s] + rng.normal(0, PHASE_SIGMA_M) for s in common}
        rb = {s: np.linalg.norm(sp[s] - B) for s in common}
        DDL[t] = np.array([(Lr[s] - Lb[s]) - (Lr[ref] - Lb[ref]) for s in others])
        DD_range_b[t] = np.array([(rb[s] - rb[ref]) for s in others])

    def _build(x, fixed_int=None):
        """Sagradi LS sustav A u = b. fixed_int=None -> float (dx+Ndd), inace samo dx."""
        rowsA, rowsb = [], []
        for t in times:
            sp = sat_pos[t]
            rho = {s: np.linalg.norm(sp[s] - x) for s in common}
            los = {s: (sp[s] - x) / rho[s] for s in common}
            for k, s in enumerate(others):
                Cc = (rho[s] - rho[ref]) - DD_range_b[t][k]
                coef_dx = -(los[s] - los[ref])
                if fixed_int is None:
                    row = np.zeros(3 + m)
                    row[:3] = coef_dx
                    row[3 + k] = LAMBDA1
                    rowsA.append(row)
                    rowsb.append(DDL[t][k] - Cc)
                else:
                    rowsA.append(coef_dx)
                    rowsb.append(DDL[t][k] - Cc - LAMBDA1 * fixed_int[k])
        return np.array(rowsA), np.array(rowsb)

    # --- FLOAT: zajednički Gauss-Newton za baseline + realne neodređenosti ---
    x = B.copy()
    Ndd_float = np.zeros(m)
    for _ in range(10):
        A, b = _build(x, fixed_int=None)
        u, *_ = np.linalg.lstsq(A, b, rcond=None)
        dx, Ndd_float = u[:3], u[3:]
        x = x + dx
        if np.linalg.norm(dx) < 1e-4:
            break
    x_float = x.copy()

    # --- FIKSIRANJE: zaokruži na cijele brojeve ---
    Ndd_fixed = np.round(Ndd_float).astype(int)

    # --- FIXED: Gauss-Newton za baseline uz fiksne cijele brojeve ---
    x = B.copy()
    for _ in range(10):
        A, b = _build(x, fixed_int=Ndd_fixed)
        dx, *_ = np.linalg.lstsq(A, b, rcond=None)
        x = x + dx
        if np.linalg.norm(dx) < 1e-5:
            break
    x_fixed = x.copy()

    return dict(
        baseline_m=float(np.linalg.norm(R - B)),
        n_common=len(common), n_epochs=n_epochs,
        float_err_m=float(np.linalg.norm(x_float - R)),
        fixed_err_m=float(np.linalg.norm(x_fixed - R)),
        ar_success=bool(np.array_equal(Ndd_fixed, Ndd_true)),
    )


def main():
    p = argparse.ArgumentParser(description="Carrier-phase RTK demo (cm-precizno).")
    p.add_argument("--lat", type=float, default=45.815, help="rover širina [°]")
    p.add_argument("--lon", type=float, default=15.982, help="rover dužina [°]")
    p.add_argument("--alt", type=float, default=120.0)
    p.add_argument("--base-east-km", type=float, default=5.0, help="baza istočno od rovera [km]")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--dt", type=float, default=30.0, help="razmak epoha [s]")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    # baza pomaknuta istočno za nekoliko km (kratka baza)
    dlon = (args.base_east_km * 1000.0) / (6378137.0 * np.cos(np.radians(args.lat))) * (180.0 / np.pi)
    res = rtk_solve((args.lat, args.lon, args.alt),
                    (args.lat, args.lon + dlon, args.alt),
                    n_epochs=args.epochs, dt_epoch=args.dt, seed=args.seed)
    if res is None:
        print("Premalo zajedničkih satelita kroz sve epohe — povećaj epochs/dt ili smanji mask.")
        return

    print("Carrier-phase RTK")
    print("-" * 44)
    print(f"Baseline (baza-rover):    {res['baseline_m']/1000:8.2f} km")
    print(f"Zajednički sateliti:      {res['n_common']:8d}")
    print(f"Epoha:                    {res['n_epochs']:8d}")
    print(f"Integer ambiguity fixed:  {'DA' if res['ar_success'] else 'NE':>8}")
    print("-" * 44)
    print(f"Float rješenje:           {res['float_err_m']:8.3f} m")
    print(f"Fixed rješenje:           {res['fixed_err_m']:8.3f} m   (RTK)")
    print(f"(kodno rješenje je reda ~desetci m — vidi benchmark.py)")


if __name__ == "__main__":
    main()
