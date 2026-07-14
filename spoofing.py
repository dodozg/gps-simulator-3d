"""Spoofing / jamming laboratorij — napadi na GNSS i ponašanje EKF/RAIM obrane.

Napadi se ubrizgavaju na razinu MJERENJA: nakon što prijemnik primi signale
(`receive_signals`), a prije rješavanja (`solve_position`), izmijenimo listu
`received_signals` (pseudoudaljenosti / izbačeni sateliti). Tako napad prolazi
kroz PRAVI EKF i RAIM iz `receiver.py`, pa se vidi što obrana stvarno hvata.

Modelirani napadi:

  * Jamming — ometač podiže šumni pod (J/N u dB). Sateliti niske elevacije
    (slabiji C/N0) prvi ispadaju iz praćenja; preostalima raste šum. Rezultat:
    manje satelita, veći GDOP, na kraju gubitak fixa. RAIM tu ne pomaže (nije
    riječ o lažnim mjerenjima nego o gubitku signala).

  * Meaconing (uniformni) — napadač snima i s kašnjenjem reemitira SVE signale,
    dodajući istu udaljenost svima. Kako je pomak zajednički, EKF ga upije u sat
    prijemnika => pozicija se NE pomiče, RAIM šuti. Lekcija: uniformni meacon sam
    po sebi ne mice poziciju.

  * Koordinirani spoof (seamless takeover) — napadač šalje MEĐUSOBNO KONZISTENTNA
    lažna mjerenja koja glatko povlače rješenje na ciljnu točku. Reziduali ostaju
    ~0 pa RAIM NIKAD ne alarmira — pozicija tiho odšeta. Ovo je temeljno
    ograničenje RAIM-a (detektira nekonzistentnost, ne laž po sebi).

  * Naivni multi-SV spoof — nekoliko satelita dobije velike NEZAVISNE pomake.
    Robusni RAIM (MAD, iterativno) ih izolira dok je pokvarenih manje od većine;
    kad ih je previše, RAIM se slomi. Veže se na poboljšani RAIM (#2).

Pokretanje:
    python spoofing.py --attack coordinated --offset-e 600
    python spoofing.py --attack jamming --js-db 34
    python spoofing.py --attack naive --n 2 --bias 5000
    python spoofing.py --attack meaconing --delay 4000
    (dodaj --plot za PNG s grafom greške/RAIM/satelita)
"""
import argparse
import numpy as np

from satellite import WalkerDeltaConstellation
from receiver import Receiver
from utils import lla_to_ecef

TRACK_THRESHOLD_DBHZ = 30.0    # ispod ovog C/N0 prijemnik gubi zabravu na satelit


def _enu_basis(rx_pos):
    """Ortonormirana ENU baza (istok, sjever, gore) u točki rx_pos (ECEF)."""
    up = rx_pos / np.linalg.norm(rx_pos)
    east = np.cross(np.array([0.0, 0.0, 1.0]), up)
    n = np.linalg.norm(east)
    east = east / n if n > 1e-9 else np.array([1.0, 0.0, 0.0])
    north = np.cross(up, east)
    return east, north, up


def _elevation(sat_pos, rx_pos):
    up = rx_pos / np.linalg.norm(rx_pos)
    v = sat_pos - rx_pos
    return np.arcsin(np.clip(np.dot(up, v / np.linalg.norm(v)), -1.0, 1.0))


def _ramp(t, start, end):
    """Glatki 0->1 faktor kroz prozor napada (0 prije, 1 poslije)."""
    if t <= start:
        return 0.0
    if t >= end:
        return 1.0
    return (t - start) / (end - start)


# --- Napadi -------------------------------------------------------------------
class Attack:
    name = "none"
    desc = "bez napada"

    def apply(self, signals, t, rx_pos, rng):
        """Izmijeni listu 'signals' (received_signals) na mjestu. Vrati opis stanja."""
        return


class NoAttack(Attack):
    pass


class Jamming(Attack):
    name = "jamming"

    def __init__(self, js_db=35.0, start=60.0, end=240.0):
        self.js_db = js_db
        self.start, self.end = start, end
        self.desc = f"ometanje: J/N do {js_db:.0f} dB (t={start:.0f}-{end:.0f} s)"

    def apply(self, signals, t, rx_pos, rng):
        js = self.js_db * _ramp(t, self.start, self.end)
        if js <= 0:
            return
        survivors = []
        for sig in signals:
            el = _elevation(sig['sat_pos'], rx_pos)
            cn0 = 37.0 + 10.0 * np.sin(max(el, 0.0))     # ~37 dB-Hz horizont, ~47 zenit
            eff = cn0 - js
            if eff < TRACK_THRESHOLD_DBHZ:
                continue                                   # signal potonuo u šum -> gubitak
            # preostalima raste šum kako se približavaju pragu
            margin = eff - TRACK_THRESHOLD_DBHZ
            extra_sigma = 3.0 * 10 ** (max(0.0, 8.0 - margin) / 20.0)
            sig['pseudorange'] += rng.normal(0.0, min(extra_sigma, 60.0))
            survivors.append(sig)
        signals[:] = survivors


class Meaconing(Attack):
    name = "meaconing"

    def __init__(self, delay_m=4000.0, start=60.0, end=240.0):
        self.delay_m = delay_m
        self.start, self.end = start, end
        self.desc = f"meaconing: uniformno kašnjenje {delay_m:.0f} m (t={start:.0f}-{end:.0f} s)"

    def apply(self, signals, t, rx_pos, rng):
        d = self.delay_m * _ramp(t, self.start, self.end)
        for sig in signals:
            sig['pseudorange'] += d                        # isti pomak SVIMA


class CoordinatedSpoof(Attack):
    name = "coordinated"

    def __init__(self, offset_e=600.0, offset_n=0.0, offset_u=0.0, start=60.0, end=240.0):
        self.off = np.array([offset_e, offset_n, offset_u], float)
        self.start, self.end = start, end
        self.desc = (f"koordinirani spoof: povlačenje na E{offset_e:+.0f} N{offset_n:+.0f} "
                     f"U{offset_u:+.0f} m (t={start:.0f}-{end:.0f} s)")
        self._target = None

    def target_ecef(self, rx_pos):
        if self._target is None:
            e, n, u = _enu_basis(rx_pos)
            self._target = rx_pos + e * self.off[0] + n * self.off[1] + u * self.off[2]
        return self._target

    def apply(self, signals, t, rx_pos, rng):
        f = _ramp(t, self.start, self.end)
        if f <= 0:
            return
        target = self.target_ecef(rx_pos)
        for sig in signals:
            bp = sig['broadcast_pos']
            # glatko zamijeni geometriju istinite točke geometrijom ciljne točke;
            # sat prijemnika i šum ostaju netaknuti => reziduali ~0, RAIM ne vidi
            delta = np.linalg.norm(bp - target) - np.linalg.norm(bp - rx_pos)
            sig['pseudorange'] += f * delta


class NaiveMultiSpoof(Attack):
    name = "naive"

    def __init__(self, n=2, bias_m=5000.0, start=60.0, end=240.0):
        self.n = n
        self.bias_m = bias_m
        self.start, self.end = start, end
        self.desc = f"naivni multi-SV: {n} satelita x ±{bias_m:.0f} m nezavisno (t={start:.0f}-{end:.0f} s)"

    def apply(self, signals, t, rx_pos, rng):
        if _ramp(t, self.start, self.end) <= 0:
            return
        for k, sig in enumerate(signals[:self.n]):
            sig['pseudorange'] += self.bias_m * (1.0 if k % 2 == 0 else -1.0)


ATTACKS = {a.name: a for a in (NoAttack, Jamming, Meaconing, CoordinatedSpoof, NaiveMultiSpoof)}


# --- Runner -------------------------------------------------------------------
def run_attack(lat, lon, alt, attack, seconds=300, seed=1234):
    """Vrti scenarij s napadom kroz PRAVI EKF/RAIM. Vrati metrike po epohama."""
    rng = np.random.default_rng(seed)
    con = WalkerDeltaConstellation(rng=rng)
    for s in con.satellites:
        s.is_spoofed = False                    # ugašen ugrađeni demo-spoof; napad kontrolira lab

    gt = np.array(lla_to_ecef(lat, lon, alt))
    rx = Receiver(gt, rng=rng)

    times, errors, gdops, tracked = [], [], [], []
    target_err, alarms, fix_lost = [], [], []
    target = attack.target_ecef(gt) if isinstance(attack, CoordinatedSpoof) else None

    for t in range(seconds):
        con.update_all(float(t))
        rx.receive_signals(con, float(t))
        attack.apply(rx.received_signals, float(t), gt, rng)   # <-- napad na mjerenja
        n_tracked = len(rx.received_signals)
        pos, gdop = rx.solve_position()

        times.append(t)
        tracked.append(n_tracked)
        if pos is None:
            fix_lost.append(t)
            continue
        errors.append((t, float(np.linalg.norm(pos - gt))))
        if gdop is not None:
            gdops.append(gdop)
        if target is not None:
            target_err.append((t, float(np.linalg.norm(pos - target))))
        if rx.raim_alarm:
            alarms.append((t, rx.raim_alarm))

    return dict(
        times=np.array(times), tracked=np.array(tracked),
        errors=errors, gdops=np.array(gdops),
        target_err=target_err, alarms=alarms, fix_lost=fix_lost,
        attack_name=attack.name, attack_desc=attack.desc,
        window=(getattr(attack, "start", 0.0), getattr(attack, "end", 0.0)),
        target=target,
    )


def _err_after(errors, t0):
    vals = [e for (t, e) in errors if t >= t0]
    return np.array(vals) if vals else np.array([0.0])


def report(data):
    start, end = data["window"]
    print(f"Napad: {data['attack_desc']}")
    print("-" * 60)
    err_all = np.array([e for _, e in data["errors"]]) if data["errors"] else np.array([])
    pre = _err_after([e for e in data["errors"] if e[0] < start], 0)
    dur = _err_after(data["errors"], start)
    print(f"Riješenih epoha:          {len(data['errors']):5d} / {len(data['times'])}")
    print(f"Praćenih satelita (min):  {int(data['tracked'].min()):5d}")
    print(f"Gubitak fixa (epoha):     {len(data['fix_lost']):5d}")
    if len(data["gdops"]):
        print(f"GDOP (median):            {np.median(data['gdops']):8.2f}")
    print(f"Greška prije napada:      {np.median(pre):8.1f} m")
    print(f"Greška za napada (median):{np.median(dur):8.1f} m")
    print(f"Greška za napada (max):   {dur.max():8.1f} m")
    if data["target_err"]:
        te = np.array([e for t, e in data["target_err"] if t >= end - 1])
        if len(te):
            print(f"Udaljenost od CILJA spoofa:{np.median(te):7.1f} m  (0 = potpuno preuzeto)")
    print(f"RAIM alarma:              {len(data['alarms']):5d}")
    if data["alarms"]:
        t, msg = data["alarms"][0]
        print(f"  prvi @ t={t}s: {msg}")
    else:
        print("  (RAIM nije alarmirao)")


def plot(data, out="spoofing.png", loc=""):
    """Opcionalni graf: greška, praćeni sateliti, RAIM/gubitak fixa kroz vrijeme."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bg, fg, grid = "#0d1117", "#e6edf3", "#30363d"
    green, red, cyan, amber = "#58d364", "#f8776a", "#39c5cf", "#e3b341"
    start, end = data["window"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                                   gridspec_kw=dict(height_ratios=[2, 1]))
    fig.patch.set_facecolor(bg)
    for ax in (ax1, ax2):
        ax.set_facecolor(bg)
        ax.axvspan(start, end, color=amber, alpha=0.10)
        for sp in ax.spines.values():
            sp.set_color(grid)
        ax.tick_params(colors=fg)
        ax.grid(True, color=grid, alpha=0.5, lw=0.5)

    if data["errors"]:
        te, ve = zip(*data["errors"])
        ax1.plot(te, ve, color=green, lw=1.6, label="greška vs prava pozicija")
    if data["target_err"]:
        tt, vt = zip(*data["target_err"])
        ax1.plot(tt, vt, color=red, lw=1.4, ls="--", label="udaljenost od cilja spoofa")
    for (t, _) in data["alarms"]:
        ax1.axvline(t, color=cyan, alpha=0.35, lw=0.8)
    for t in data["fix_lost"]:
        ax1.axvline(t, color=red, alpha=0.25, lw=0.8)
    ax1.set_ylabel("greška [m]", color=fg)
    ax1.set_title(f"Spoofing/jamming lab — {data['attack_desc']}", color=fg)
    ax1.legend(facecolor=bg, edgecolor=grid, labelcolor=fg, fontsize=8, loc="upper left")

    ax2.plot(data["times"], data["tracked"], color=cyan, lw=1.4)
    ax2.set_ylabel("praćeni sateliti", color=fg)
    ax2.set_xlabel("vrijeme [s]", color=fg)
    ax2.set_ylim(0, max(8, data["tracked"].max() + 1))

    fig.suptitle(f"RAIM alarma: {len(data['alarms'])}   gubitak fixa: {len(data['fix_lost'])} epoha   {loc}",
                 color=fg, y=0.02, fontsize=9)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out, dpi=110, facecolor=bg)
    plt.close(fig)
    return out


def _build_attack(args):
    if args.attack == "jamming":
        return Jamming(args.js_db, args.start, args.end)
    if args.attack == "meaconing":
        return Meaconing(args.delay, args.start, args.end)
    if args.attack == "coordinated":
        return CoordinatedSpoof(args.offset_e, args.offset_n, args.offset_u, args.start, args.end)
    if args.attack == "naive":
        return NaiveMultiSpoof(args.n, args.bias, args.start, args.end)
    return NoAttack()


def main():
    p = argparse.ArgumentParser(description="GNSS spoofing/jamming laboratorij.")
    p.add_argument("--attack", choices=list(ATTACKS), default="coordinated")
    p.add_argument("--lat", type=float, default=45.815)
    p.add_argument("--lon", type=float, default=15.982)
    p.add_argument("--alt", type=float, default=120.0)
    p.add_argument("--seconds", type=int, default=300)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--start", type=float, default=60.0)
    p.add_argument("--end", type=float, default=240.0)
    # parametri po napadu
    p.add_argument("--js-db", type=float, default=35.0, help="jamming: vršni J/N [dB]")
    p.add_argument("--delay", type=float, default=4000.0, help="meaconing: kašnjenje [m]")
    p.add_argument("--offset-e", type=float, default=600.0, help="coordinated: pomak istok [m]")
    p.add_argument("--offset-n", type=float, default=0.0, help="coordinated: pomak sjever [m]")
    p.add_argument("--offset-u", type=float, default=0.0, help="coordinated: pomak gore [m]")
    p.add_argument("--n", type=int, default=2, help="naive: broj spoofanih satelita")
    p.add_argument("--bias", type=float, default=5000.0, help="naive: pomak po satelitu [m]")
    p.add_argument("--plot", action="store_true", help="spremi spoofing.png")
    args = p.parse_args()

    attack = _build_attack(args)
    data = run_attack(args.lat, args.lon, args.alt, attack, args.seconds, args.seed)
    print(f"Lokacija: LLA({args.lat}, {args.lon}, {args.alt})   seed: {args.seed}")
    report(data)
    if args.plot:
        out = plot(data, loc=f"LLA({args.lat}, {args.lon})")
        print(f"[graf] {out}")


if __name__ == "__main__":
    main()
