"""Snimanje i reprodukcija scenarija (#10) — JSON opis svijeta, deterministički run.

Scenarij fiksira SVE što određuje simulaciju: lokaciju, trajanje, sjeme RNG-a,
doba dana (ionosfera) i opcionalni kvar (spoofing/jamming). Kako svi izvori šuma
dijele jedan seedani `np.random.Generator`, reprodukcija istog JSON-a daje
BAJT-identične metrike — pa se scenariji mogu spremati, dijeliti i koristiti za
poštenu usporedbu algoritama (npr. RAIM uključen vs isključen).

    python scenario.py run scenarios/spoof_coordinated.json
    python scenario.py compare scenarios/spoof_coordinated.json      # RAIM on vs off
    python scenario.py compare scenarios/zagreb_clean.json scenarios/tokyo_terrain.json
    python scenario.py record --lat 35.68 --lon 139.69 --attack jamming --out moj.json
    python scenario.py list

Shema (JSON):
    {"name","description","lat","lon","alt","seconds","seed","iono_tow0",
     "attack": {"type": "coordinated|naive|meaconing|jamming", ...params} | null}
"""
import argparse
import glob
import json
import os
from dataclasses import dataclass, asdict, field

import numpy as np

from satellite import WalkerDeltaConstellation
from receiver import Receiver
from utils import lla_to_ecef
from spoofing import (NoAttack, Jamming, Meaconing, CoordinatedSpoof,
                      NaiveMultiSpoof)

SCENARIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios")


@dataclass
class Scenario:
    name: str = "scenarij"
    description: str = ""
    lat: float = 45.815
    lon: float = 15.982
    alt: float = 120.0
    seconds: int = 300
    seed: int = 1234
    iono_tow0: float = 50400.0
    attack: dict = field(default_factory=lambda: None)

    @staticmethod
    def load(path):
        with open(path, "r", encoding="utf-8") as f:
            return Scenario(**json.load(f))

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        return path


def build_attack(spec):
    """Napravi objekt napada iz dict specifikacije (ili NoAttack ako je None)."""
    if not spec:
        return NoAttack()
    s = dict(spec)
    kind = s.pop("type")
    ctor = {"jamming": Jamming, "meaconing": Meaconing,
            "coordinated": CoordinatedSpoof, "naive": NaiveMultiSpoof}[kind]
    return ctor(**s)


def run_scenario(scn, raim=True):
    """Odvrti scenarij kroz pravi EKF/RAIM. Vrati determinističke metrike."""
    rng = np.random.default_rng(scn.seed)
    con = WalkerDeltaConstellation(rng=rng)
    for s in con.satellites:
        s.is_spoofed = False                      # kvarove definira scenarij, ne default
    gt = np.array(lla_to_ecef(scn.lat, scn.lon, scn.alt))
    rx = Receiver(gt, rng=rng)
    rx.iono_tow0 = scn.iono_tow0
    rx.raim_enabled = raim
    attack = build_attack(scn.attack)
    win = (getattr(attack, "start", 0.0), getattr(attack, "end", 0.0))
    target = attack.target_ecef(gt) if isinstance(attack, CoordinatedSpoof) else None

    errors, gdops, nis, alarms, fix_lost = [], [], [], [], []
    win_err, target_err = [], []
    for t in range(scn.seconds):
        con.update_all(float(t))
        rx.receive_signals(con, float(t))
        attack.apply(rx.received_signals, float(t), gt, rng)
        pos, gdop = rx.solve_position()
        if pos is None:
            fix_lost.append(t)
            continue
        e = float(np.linalg.norm(pos - gt))
        errors.append(e)
        if win[0] <= t <= win[1] and scn.attack:
            win_err.append(e)
        if target is not None:
            target_err.append(float(np.linalg.norm(pos - target)))
        if gdop is not None:
            gdops.append(gdop)
        if rx.nis_dof:
            nis.append(rx.nis / rx.nis_dof)
        if rx.raim_alarm:
            alarms.append((t, rx.raim_alarm))

    errors = np.array(errors)
    conv = errors[len(errors) // 2:] if len(errors) else errors
    return dict(
        solved=len(errors), total=scn.seconds,
        median_err=float(np.median(errors)) if len(errors) else float("nan"),
        conv_mean=float(conv.mean()) if len(conv) else float("nan"),
        conv_p95=float(np.percentile(conv, 95)) if len(conv) else float("nan"),
        max_err=float(errors.max()) if len(errors) else float("nan"),
        gdop_median=float(np.median(gdops)) if gdops else float("nan"),
        nis_mean=float(np.mean(nis)) if nis else float("nan"),
        raim_alarms=len(alarms), fix_lost=len(fix_lost),
        win_median_err=float(np.median(win_err)) if win_err else None,
        takeover_m=(float(np.median(target_err[-5:])) if target_err else None),
        raim=raim,
    )


def _print_metrics(m, title):
    print(title)
    print("-" * 52)
    print(f"Riješeno / ukupno:      {m['solved']:5d} / {m['total']}")
    print(f"Greška (median):        {m['median_err']:8.1f} m")
    print(f"Konvergirano (mean):    {m['conv_mean']:8.1f} m")
    print(f"Konvergirano (95%):     {m['conv_p95']:8.1f} m")
    print(f"Maksimalna greška:      {m['max_err']:8.1f} m")
    print(f"GDOP (median):          {m['gdop_median']:8.2f}")
    print(f"NIS/dof (mean):         {m['nis_mean']:8.2f}")
    print(f"RAIM alarma:            {m['raim_alarms']:5d}")
    print(f"Gubitak fixa:           {m['fix_lost']:5d}")
    if m["win_median_err"] is not None:
        print(f"Greška za napada (med): {m['win_median_err']:8.1f} m")
    if m["takeover_m"] is not None:
        print(f"Udaljenost od cilja:    {m['takeover_m']:8.1f} m")


def cmd_run(args):
    scn = Scenario.load(args.file)
    print(f"[scenarij] {scn.name} — {scn.description}")
    print(f"LLA({scn.lat}, {scn.lon}, {scn.alt})  {scn.seconds}s  seed={scn.seed}  "
          f"napad={scn.attack['type'] if scn.attack else 'nema'}")
    print("=" * 52)
    _print_metrics(run_scenario(scn, raim=not args.no_raim), "Rezultat")


def _side_by_side(mA, mB, labA, labB):
    rows = [
        ("Riješeno", f"{mA['solved']}/{mA['total']}", f"{mB['solved']}/{mB['total']}"),
        ("Greška median [m]", f"{mA['median_err']:.1f}", f"{mB['median_err']:.1f}"),
        ("Konverg. 95% [m]", f"{mA['conv_p95']:.1f}", f"{mB['conv_p95']:.1f}"),
        ("Maks greška [m]", f"{mA['max_err']:.1f}", f"{mB['max_err']:.1f}"),
        ("GDOP median", f"{mA['gdop_median']:.2f}", f"{mB['gdop_median']:.2f}"),
        ("RAIM alarma", f"{mA['raim_alarms']}", f"{mB['raim_alarms']}"),
        ("Gubitak fixa", f"{mA['fix_lost']}", f"{mB['fix_lost']}"),
    ]
    if mA["win_median_err"] is not None or mB["win_median_err"] is not None:
        rows.append(("Greška za napada [m]",
                     "-" if mA["win_median_err"] is None else f"{mA['win_median_err']:.1f}",
                     "-" if mB["win_median_err"] is None else f"{mB['win_median_err']:.1f}"))
    print(f"{'':22s}{labA:>15s}{labB:>15s}")
    print("-" * 52)
    for name, a, b in rows:
        print(f"{name:22s}{a:>15s}{b:>15s}")


def cmd_compare(args):
    scnA = Scenario.load(args.file)
    if args.other:
        scnB = Scenario.load(args.other)
        print(f"Usporedba scenarija:  A={scnA.name}   B={scnB.name}")
        print("=" * 52)
        _side_by_side(run_scenario(scnA), run_scenario(scnB), "A", "B")
    else:
        print(f"Usporedba algoritama na scenariju: {scnA.name}  (RAIM on vs off)")
        print("=" * 52)
        _side_by_side(run_scenario(scnA, raim=True), run_scenario(scnA, raim=False),
                      "RAIM on", "RAIM off")


def cmd_record(args):
    attack = None
    if args.attack:
        attack = {"type": args.attack, "start": args.start, "end": args.end}
        if args.attack == "coordinated":
            attack["offset_e"] = args.offset_e
        elif args.attack == "naive":
            attack["n"] = args.n; attack["bias_m"] = args.bias
        elif args.attack == "meaconing":
            attack["delay_m"] = args.delay
        elif args.attack == "jamming":
            attack["js_db"] = args.js_db
    scn = Scenario(name=args.name, description=args.description, lat=args.lat,
                   lon=args.lon, alt=args.alt, seconds=args.seconds, seed=args.seed,
                   iono_tow0=args.iono_tow0, attack=attack)
    path = scn.save(args.out)
    print(f"[snimljeno] {path}")


def cmd_list(args):
    files = sorted(glob.glob(os.path.join(SCENARIO_DIR, "*.json")))
    if not files:
        print(f"Nema scenarija u {SCENARIO_DIR}")
        return
    print(f"Scenariji u {SCENARIO_DIR}:")
    for f in files:
        scn = Scenario.load(f)
        atk = scn.attack["type"] if scn.attack else "-"
        print(f"  {os.path.basename(f):28s} LLA({scn.lat},{scn.lon}) {scn.seconds}s  napad={atk}")


def main():
    p = argparse.ArgumentParser(description="Snimanje/reprodukcija GNSS scenarija (JSON).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="odvrti scenarij i ispiši metrike")
    pr.add_argument("file"); pr.add_argument("--no-raim", action="store_true")
    pr.set_defaults(func=cmd_run)

    pc = sub.add_parser("compare", help="usporedi RAIM on/off ili dva scenarija")
    pc.add_argument("file"); pc.add_argument("other", nargs="?")
    pc.set_defaults(func=cmd_compare)

    pl = sub.add_parser("list", help="popiši bundlane scenarije")
    pl.set_defaults(func=cmd_list)

    prc = sub.add_parser("record", help="snimi novi scenarij u JSON")
    prc.add_argument("--out", required=True)
    prc.add_argument("--name", default="scenarij"); prc.add_argument("--description", default="")
    prc.add_argument("--lat", type=float, default=45.815); prc.add_argument("--lon", type=float, default=15.982)
    prc.add_argument("--alt", type=float, default=120.0); prc.add_argument("--seconds", type=int, default=300)
    prc.add_argument("--seed", type=int, default=1234); prc.add_argument("--iono-tow0", type=float, default=50400.0)
    prc.add_argument("--attack", choices=["coordinated", "naive", "meaconing", "jamming"])
    prc.add_argument("--start", type=float, default=60.0); prc.add_argument("--end", type=float, default=240.0)
    prc.add_argument("--offset-e", type=float, default=600.0); prc.add_argument("--n", type=int, default=2)
    prc.add_argument("--bias", type=float, default=5000.0); prc.add_argument("--delay", type=float, default=4000.0)
    prc.add_argument("--js-db", type=float, default=40.0)
    prc.set_defaults(func=cmd_record)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
