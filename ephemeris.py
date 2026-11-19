"""GPS broadcast efemeride (IS-GPS-200) -> ECEF pozicija i sat satelita.

Ovo je PRAVI algoritam iz navigacijske poruke (IS-GPS-200, tablica 20-IV),
ne idealizirani Walker-Delta model iz `satellite.py`:

1. Keplerova orbita iz √A, e, M0, Δn (srednje gibanje korigirano), Newtonova
   iteracija Keplerove jednadžbe E − e·sinE = M.
2. Harmonijske korekcije drugog reda (Cuc/Cus — argument širine, Crc/Crs —
   radijus, Cic/Cis — inklinacija) + IDOT.
3. Zemljina rotacija: longituda uzlaznog čvora Ω = Ω0 + (Ω̇ − ω_E)·tk − ω_E·toe
   daje poziciju u ECEF okviru U TRENUTKU t (WGS-84).
4. Sat satelita: Δt_sv = af0 + af1·(t−toc) + af2·(t−toc)² + Δt_r, gdje je
   relativistički član Δt_r = F·e·√A·sinE (F = −2√μ/c²). Jednofrekvencijski
   (L1 C/A) korisnik dodatno oduzima TGD.

NAPOMENA o okviru: `sat_position(eph, t)` vraća poziciju u ECEF okviru u trenutku
odašiljanja t — BEZ korekcije za rotaciju Zemlje tijekom leta signala. Tu
korekciju (Sagnac) radi model prijemnika (`receiver.Receiver` dodaje
`physics_engine.calculate_sagnac_correction`), pa je ovdje NE smijemo dodati još
jednom (inače bi bila dvaput uračunata; vidi tests/test_realdata.py).

Konstante su one propisane u IS-GPS-200 (NE one iz physics_engine.py, koje su
za idealizirani simulator): μ = 3.986005e14, ω_E = 7.2921151467e-5.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MU_GPS = 3.986005e14            # [m^3/s^2] WGS-84 gravitacijski parametar (IS-GPS-200)
OMEGA_E_GPS = 7.2921151467e-5   # [rad/s] rotacija Zemlje (IS-GPS-200)
C_LIGHT = 299792458.0           # [m/s]
F_REL = -4.442807633e-10        # [s/√m] = −2√μ/c²
HALF_WEEK = 302400.0
SEC_PER_WEEK = 604800.0
MAX_DTOE = 7200.0               # [s] efemerida vrijedi ±2 h oko toe (standardni fit 4 h)


@dataclass
class Ephemeris:
    """Jedan GPS broadcast zapis (podskup polja RINEX navigacije, SI jedinice)."""
    prn: str                    # 'G03'
    toc: float                  # vrijeme sata [GPS s od 1980-01-06]
    af0: float                  # [s]
    af1: float                  # [s/s]
    af2: float                  # [s/s²]
    iode: float
    crs: float                  # [m]
    delta_n: float              # [rad/s]
    m0: float                   # [rad]
    cuc: float                  # [rad]
    e: float
    cus: float                  # [rad]
    sqrt_a: float               # [√m]
    toe_sow: float              # [s u GPS tjednu]
    cic: float                  # [rad]
    omega0: float               # [rad]
    cis: float                  # [rad]
    i0: float                   # [rad]
    crc: float                  # [m]
    omega: float                # [rad] argument perigeja
    omega_dot: float            # [rad/s]
    idot: float                 # [rad/s]
    week: int                   # GPS tjedan (kontinuiran, uz toe)
    sv_accuracy: float = 0.0    # [m] URA
    health: int = 0             # 0 = zdrav
    tgd: float = 0.0            # [s]
    iodc: float = 0.0
    tot: float = 0.0            # vrijeme slanja poruke [s u tjednu]
    fit_interval: float = 0.0   # [h] (0 = 4 h)

    @property
    def toe(self):
        """Referentno vrijeme efemeride kao GPS sekunde od 1980-01-06."""
        return self.week * SEC_PER_WEEK + self.toe_sow

    @property
    def a(self):
        return self.sqrt_a ** 2


def _wrap_tk(tk):
    """Prijelaz preko granice tjedna (IS-GPS-200: tk ∈ [−302400, 302400])."""
    if tk > HALF_WEEK:
        tk -= SEC_PER_WEEK
    elif tk < -HALF_WEEK:
        tk += SEC_PER_WEEK
    return tk


def eccentric_anomaly(eph: Ephemeris, t):
    """Ekscentrična anomalija E [rad] u trenutku t (GPS s)."""
    a = eph.sqrt_a ** 2
    n = np.sqrt(MU_GPS / a ** 3) + eph.delta_n
    tk = _wrap_tk(t - eph.toe)
    M = eph.m0 + n * tk
    E = M
    for _ in range(30):
        dE = (E - eph.e * np.sin(E) - M) / (1.0 - eph.e * np.cos(E))
        E -= dE
        if abs(dE) < 1e-14:
            break
    return E


def sat_position(eph: Ephemeris, t):
    """ECEF pozicija satelita [m] u trenutku t (GPS s), okvir ECEF u trenutku t.

    Vraća (pos ndarray(3), E). Vidi napomenu o Sagnac članu u zaglavlju modula.
    """
    a = eph.sqrt_a ** 2
    tk = _wrap_tk(t - eph.toe)
    E = eccentric_anomaly(eph, t)
    sinE, cosE = np.sin(E), np.cos(E)
    nu = np.arctan2(np.sqrt(1.0 - eph.e ** 2) * sinE, cosE - eph.e)   # prava anomalija
    phi = nu + eph.omega                                                # argument širine
    s2, c2 = np.sin(2.0 * phi), np.cos(2.0 * phi)
    du = eph.cus * s2 + eph.cuc * c2
    dr = eph.crs * s2 + eph.crc * c2
    di = eph.cis * s2 + eph.cic * c2
    u = phi + du
    r = a * (1.0 - eph.e * cosE) + dr
    inc = eph.i0 + di + eph.idot * tk
    xp, yp = r * np.cos(u), r * np.sin(u)                               # u orbitalnoj ravnini
    Om = eph.omega0 + (eph.omega_dot - OMEGA_E_GPS) * tk - OMEGA_E_GPS * eph.toe_sow
    cO, sO, ci = np.cos(Om), np.sin(Om), np.cos(inc)
    pos = np.array([xp * cO - yp * ci * sO,
                    xp * sO + yp * ci * cO,
                    yp * np.sin(inc)])
    return pos, E


def relativistic_correction(eph: Ephemeris, t):
    """Relativistički član sata Δt_r = F·e·√A·sinE [s] (ekscentrična orbita)."""
    return F_REL * eph.e * eph.sqrt_a * np.sin(eccentric_anomaly(eph, t))


def sat_clock(eph: Ephemeris, t, include_relativity=True, l1_tgd=False):
    """Pomak sata satelita Δt_sv [s] u trenutku t (GPS s).

    include_relativity: dodaj Δt_r (za navigaciju DA; za usporedbu s IGS SP3
    satovima NE, jer ih IGS daje bez periodičkog relativističkog člana).
    l1_tgd: jednofrekvencijski L1 C/A korisnik oduzima TGD (IS-GPS-200 20.3.3.3.3.2).
    """
    dt = _wrap_tk(t - eph.toc)
    dts = eph.af0 + eph.af1 * dt + eph.af2 * dt * dt
    if include_relativity:
        dts += relativistic_correction(eph, t)
    if l1_tgd:
        dts -= eph.tgd
    return dts


def sat_velocity(eph: Ephemeris, t, h=0.5):
    """ECEF brzina [m/s] centralnom diferencijom (u rotirajućem ECEF okviru)."""
    p1, _ = sat_position(eph, t - h)
    p2, _ = sat_position(eph, t + h)
    return (p2 - p1) / (2.0 * h)


def select_ephemeris(ephs, t, max_dtoe=MAX_DTOE, healthy_only=True):
    """Odaberi efemeridu s najbližim toe za trenutak t (ili None ako nijedna ne vrijedi).

    ephs: lista `Ephemeris` za JEDAN satelit. Zapis vrijedi ako je |t − toe| ≤
    max_dtoe (zadano 2 h) i, uz healthy_only, ako je SV health == 0. Kod
    izjednačenja (ista udaljenost) prednost ima noviji zapis (kasniji toe / veći IODE).
    """
    best, best_d = None, None
    for e in ephs:
        if healthy_only and e.health != 0:
            continue
        d = abs(t - e.toe)
        if d > max_dtoe:
            continue
        if best is None or d < best_d or (d == best_d and e.toe >= best.toe):
            best, best_d = e, d
    return best
