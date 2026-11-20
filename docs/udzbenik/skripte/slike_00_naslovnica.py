"""Crta slike/naslovnica.svg: tehnički crtež Zemlje, orbita i satelita koji se udesno
raspada u mrežu pravih pseudoudaljenosti iz simulatora (km).

Isti jezik kao naslovnica knjige „Od vozača do mehaničara”: tanke linije u petrolej
boji, narančasti naglasci, nasumičnost sa stalnim sjemenom (izlaz je uvijek isti).
Pokretanje: python docs/udzbenik/build.py --slike 00
"""
import math
import os
import random

import numpy as np

from stil import SLIKE

PETROL, SIGNAL, INK, MUTED, LINE = "#0e4f63", "#c2570a", "#16222b", "#7d8d97", "#9fb1ba"
W, H = 595, 360
CW, CH = 50, 15                     # ćelija mreže brojeva
POCETAK, PUNO = 300, 520            # x gdje raspad počinje i gdje je potpun
rnd = random.Random(2026)


def udio(x):
    t = max(0.0, min(1.0, (x - POCETAK) / (PUNO - POCETAK)))
    return t * t * (3 - 2 * t)


def pseudoudaljenosti(n):
    """Prave pseudoudaljenosti (km) iz simulatora: Zagreb, samo GPS, uzastopne epohe."""
    from receiver import Receiver
    from satellite import WalkerDeltaConstellation
    from utils import lla_to_ecef
    rng = np.random.default_rng(7)
    con = WalkerDeltaConstellation(rng=rng)
    for s in con.satellites:
        s.is_spoofed = False
    rx = Receiver(np.array(lla_to_ecef(45.815, 15.982, 120.0)), rng=rng)
    out = []
    t = 0
    while len(out) < n:
        con.update_all(float(t))
        sig = rx.receive_signals(con, float(t))
        rx.solve_position()
        # pseudoudaljenost bez pomaka sata prijemnika (inače svi narastu za 300 m/s)
        out += [(s["pseudorange"] - rx.meas.clock_bias * 299792458.0) / 1000.0 for s in sig]
        t += 37
    return out[:n]


def fmt(km):
    cijeli = int(km)
    s = f"{cijeli:,}".replace(",", " ")
    return f"{s},{int(round((km - cijeli) * 100)) % 100:02d}"


class Crtez:
    def __init__(self):
        self.el = []

    def put(self, tocke, boja=PETROL, sirina=0.8, crtkano=None, zatvoreno=False):
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in tocke) + (" Z" if zatvoreno else "")
        dash = f' stroke-dasharray="{crtkano}"' if crtkano else ""
        self.el.append(f'<path d="{d}" fill="none" stroke="{boja}" stroke-width="{sirina}" '
                       f'stroke-linecap="round" stroke-linejoin="round"{dash}/>')

    def krug(self, cx, cy, r, boja=PETROL, sirina=0.8, ispuna="none"):
        self.el.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{ispuna}" stroke="{boja}" stroke-width="{sirina}"/>')


def elipsa(cx, cy, a, b, rot, t0=0.0, t1=2 * math.pi, n=240):
    c, s = math.cos(rot), math.sin(rot)
    pts = []
    for k in range(n + 1):
        t = t0 + (t1 - t0) * k / n
        x, y = a * math.cos(t), b * math.sin(t)
        pts.append((cx + x * c - y * s, cy + x * s + y * c))
    return pts


def main():
    c = Crtez()
    # Zemlja: veliki krug čije se gornje lice vidi u donjem lijevom dijelu
    EX, EY, ER = 150, 540, 330
    c.krug(EX, EY, ER, PETROL, 1.4)
    # paralele i meridijani (ortografska projekcija, os nagnuta)
    nagib = math.radians(18)
    for lat in range(-60, 90, 15):
        pts = []
        for lon in range(-180, 181, 3):
            la, lo = math.radians(lat), math.radians(lon)
            x, y, z = math.cos(la) * math.sin(lo), math.sin(la), math.cos(la) * math.cos(lo)
            y2, z2 = y * math.cos(nagib) + z * math.sin(nagib), -y * math.sin(nagib) + z * math.cos(nagib)
            pts.append((EX + ER * x, EY - ER * y2) if z2 > 0 else None)
        _po_dijelovima(c, pts, LINE, 0.45)
    for lon in range(-180, 180, 15):
        pts = []
        for lat in range(-90, 91, 3):
            la, lo = math.radians(lat), math.radians(lon + 8)
            x, y, z = math.cos(la) * math.sin(lo), math.sin(la), math.cos(la) * math.cos(lo)
            y2, z2 = y * math.cos(nagib) + z * math.sin(nagib), -y * math.sin(nagib) + z * math.cos(nagib)
            pts.append((EX + ER * x, EY - ER * y2) if z2 > 0 else None)
        _po_dijelovima(c, pts, LINE, 0.45)

    # orbite (MEO): elipse oko središta Zemlje
    orbite = [(560, 455, math.radians(-8)), (500, 420, math.radians(10)), (640, 500, math.radians(-22))]
    for a, b, r in orbite:
        c.put(elipsa(EX, EY, a, b, r, math.pi * 1.02, math.pi * 1.98), PETROL, 0.7)
    # prijemnik na Zemlji i zaštitni krug
    kut = math.radians(14)
    RX, RY = EX + ER * math.sin(kut), EY - ER * math.cos(kut)
    sateliti = []
    for (a, b, r), kutovi in zip(orbite, ([1.30, 1.47, 1.66], [1.20, 1.56], [1.36, 1.55, 1.74])):
        for k in kutovi:
            x, y = elipsa(EX, EY, a, b, r, math.pi * k, math.pi * k, 1)[0]
            if 12 < y < RY - 40 and 34 < x < W:
                sateliti.append((x, y))
    for x, y in sateliti:
        c.put([(x, y), (RX, RY)], SIGNAL, 0.6, crtkano="2.5 2.5")
    for x, y in sateliti:
        _satelit(c, x, y, rnd.uniform(-0.5, 0.5))
    c.krug(RX, RY, 3.0, SIGNAL, 1.2, ispuna=SIGNAL)
    for r in (9, 16):
        c.krug(RX, RY, r, SIGNAL, 0.6)

    # mreža brojeva: ćelija postaje broj s vjerojatnošću koja raste udesno
    stupaca, redaka = (W - 14) // CW, H // CH + 1      # zadnji stupac završava prije ruba stranice
    x0 = W - 14 - stupaca * CW
    brojevi = pseudoudaljenosti(stupaca * redaka)
    tekst, maske = [], []
    k = 0
    for s in range(stupaca):
        for r in range(redaka):
            x, y = x0 + s * CW, r * CH
            if rnd.random() < udio(x + CW / 2):
                maske.append(f'<rect x="{x}" y="{y}" width="{CW}" height="{CH}" fill="#ffffff"/>')
                boja = SIGNAL if rnd.random() < 0.07 else (PETROL if rnd.random() < 0.55 else MUTED)
                tekst.append(f'<text x="{x + CW - 3}" y="{y + CH - 4.2}" text-anchor="end" '
                             f'font-family="JetBrains Mono" font-size="7" fill="{boja}">{fmt(brojevi[k])}</text>')
            k += 1
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
           '<rect width="100%" height="100%" fill="#ffffff"/>', *c.el, *maske, *tekst, "</svg>"]
    put = os.path.join(SLIKE, "naslovnica.svg")
    with open(put, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))
    print("  slika: slike/naslovnica.svg")


def _po_dijelovima(c, pts, boja, sirina):
    seg = []
    for p in pts + [None]:
        if p is None or not (-5 < p[1] < H + 5):
            if len(seg) > 1:
                c.put(seg, boja, sirina)
            seg = []
        else:
            seg.append(p)


def _satelit(c, x, y, rot):
    """Linijski satelit: tijelo, dva solarna krila, antena."""
    cs, sn = math.cos(rot), math.sin(rot)

    def T(u, v):
        return (x + u * cs - v * sn, y + u * sn + v * cs)
    c.put([T(-4, -4), T(4, -4), T(4, 4), T(-4, 4)], PETROL, 1.0, zatvoreno=True)
    for strana in (-1, 1):
        u0, u1 = strana * 5, strana * 21
        c.put([T(u0, 0), T(strana * 7, 0)], PETROL, 0.8)
        c.put([T(strana * 7, -3.5), T(u1, -3.5), T(u1, 3.5), T(strana * 7, 3.5)], PETROL, 0.8, zatvoreno=True)
        for u in range(1, 4):
            uu = strana * (7 + u * 3.5)
            c.put([T(uu, -3.5), T(uu, 3.5)], PETROL, 0.4)
    c.put([T(0, 4), T(0, 8)], PETROL, 0.8)
    c.krug(*T(0, 9.5), 1.6, PETROL, 0.8)


if __name__ == "__main__":
    main()
