"""Prave orbite: stvarni GNSS sateliti iz CelesTrak GP elemenata (SGP4), u pravom UTC-u.

Živa simulacija inače vrti idealiziranu Walker konstelaciju (predvidljiva, dobra za
lekcije). Ovaj modul daje PRAVE satelite (GPS, Galileo, GLONASS, BeiDou — uključujući
BeiDou GEO/IGSO) za zadani trenutak ("sada" ili odabrani datum), pa se skyplot
poklapa s onim što pokazuje mobitel.

- **Podaci**: CelesTrak GP elementi (OMM JSON; grupe gps-ops, galileo, glo-ops,
  beidou). `load_gp()` čita lokalni cache (svjež < 12 h), po potrebi skida nove
  (`fetch_gp`, samo na izričit zahtjev — REST /api/orbits/refresh) ili pada na
  ugrađenu snimku `data/gnss_gp_snapshot.json`.
- **Propagacija**: SGP4/SDP4 (`sgp4` paket — GNSS orbite su "deep space", period
  ~12 h, pa jednostavan Kepler + J2 nije dovoljan). Rezultat je u TEME okviru;
  ECEF = Rz(GMST)·TEME (bez polarnog gibanja/nutacije — ~100 m na visini GNSS-a,
  zanemarivo za simulaciju). Točnost GP elemenata za GNSS je red ~km, što je za
  prikaz neba i simulaciju mjerenja (gdje je orbita "istina") sasvim dovoljno; za
  preciznu obradu stvarnih podataka koristi `ephemeris.py` (broadcast efemeride).
- **Sučelje**: `RealConstellation` je zamjena za `MultiGNSSConstellation`
  (`.satellites`, `.update_all(t, ideal)`, `.sys_bias`, `.rng`). Sim-vrijeme t [s]
  teče od zadane epohe (`utc_at(t)`), a `gmst(t)` daje kut rotacije Zemlje za crtanje.
"""
import datetime as dt
import json
import math
import os
import re
import time
import urllib.request

import numpy as np

from physics_engine import (evolve_ephemeris_error, get_dynamic_relativistic_offset,
                            simulate_clock_noise)
from satellite import GNSS_SYSTEMS, Satellite

ROOT = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_PATH = os.path.join(ROOT, "data", "gnss_gp_snapshot.json")
CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json"
GROUPS = {"gps-ops": "GPS", "galileo": "GAL", "glo-ops": "GLO", "beidou": "BDS"}
CACHE_MAX_AGE_S = 12 * 3600
GPS_UTC_LEAP_S = 18.0          # GPS vrijeme = UTC + 18 s (od 2017.)
MU_KM = 398600.4418            # [km^3/s^2] za veliku poluos iz srednjeg gibanja
OMEGA_E = 7.2921158553e-5      # [rad/s]


def cache_path():
    base = os.environ.get("GPSWEB_CACHE") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache"),
        "gps-simulator-3d")
    return os.path.join(base, "gnss_gp_cache.json")


def _now_utc():
    return dt.datetime.now(dt.timezone.utc)


def fetch_gp(timeout=15.0):
    """Skini aktualne GP elemente s CelesTraka i spremi ih u cache. Vrati dict podataka."""
    groups = {}
    for g in GROUPS:
        req = urllib.request.Request(CELESTRAK_URL.format(group=g),
                                     headers={"User-Agent": "gps-simulator-3d"})
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (fiksni https URL)
            data = json.loads(r.read().decode("utf-8"))
        if not isinstance(data, list) or not data:
            raise ValueError(f"CelesTrak: prazan odgovor za grupu {g}")
        groups[g] = data
    out = {"source": "CelesTrak GP (https://celestrak.org), OMM JSON",
           "fetched_utc": _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"), "groups": groups}
    path = cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f)
    os.replace(tmp, path)
    return out


def load_gp(allow_fetch=False):
    """GP elementi: svjež cache → (opcionalno) CelesTrak → ugrađena snimka.

    Vraća (data, origin) gdje je origin 'cache' | 'download' | 'snapshot'."""
    path = cache_path()
    try:
        if os.path.isfile(path) and time.time() - os.path.getmtime(path) < CACHE_MAX_AGE_S:
            with open(path, encoding="utf-8") as f:
                return json.load(f), "cache"
    except (OSError, ValueError):
        pass
    if allow_fetch:
        try:
            return fetch_gp(), "download"
        except Exception:      # mreža nedostupna -> padamo na stariji cache / snimku
            pass
    try:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f), "cache"
    except (OSError, ValueError):
        pass
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f), "snapshot"


def sat_label(name, system, norad):
    """Kratka oznaka satelita iz CelesTrak imena: G22, E101, R720, C06."""
    m = re.search(r"PRN\s*(\d+)", name)
    if system == "GPS" and m:
        return f"G{int(m.group(1)):02d}"
    m = re.search(r"\((C\d+)\)", name)
    if system == "BDS" and m:
        return m.group(1)
    m = re.search(r"GSAT0*(\d+)", name)
    if system == "GAL" and m:
        return f"E{int(m.group(1)):03d}"
    m = re.search(r"\((\d+)[A-Z]?\)", name)
    if system == "GLO" and m:
        return f"R{m.group(1)}"
    return f"{system[0]}{norad}"


def _parse_epoch(s):
    if isinstance(s, dt.datetime):
        return s.astimezone(dt.timezone.utc)
    s = str(s).strip()
    if s.lower() in ("", "now", "sada"):
        return _now_utc()
    s = s.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def _jd(d):
    from sgp4.api import jday
    return jday(d.year, d.month, d.day, d.hour, d.minute, d.second + d.microsecond * 1e-6)


def gmst_rad(d):
    from sgp4.propagation import gstime
    jd, fr = _jd(d)
    return gstime(jd + fr)


def _teme_to_ecef(r_km, v_kms, theta):
    c, s = math.cos(theta), math.sin(theta)
    x, y, z = r_km
    r = np.array([c * x + s * y, -s * x + c * y, z]) * 1000.0
    vx, vy, vz = v_kms
    v = np.array([c * vx + s * vy, -s * vx + c * vy, vz]) * 1000.0
    # brzina u rotirajućem okviru: v_ecef = R·v_teme − ω × r_ecef
    v += np.array([OMEGA_E * r[1], -OMEGA_E * r[0], 0.0])
    return r, v


class RealSatellite(Satellite):
    """Stvarni satelit: pozicija iz SGP4, sve ostalo (sat, efemeride, signal) kao `Satellite`."""

    def __init__(self, omm, system, epoch_utc, t0=0.0):
        from sgp4 import omm as omm_mod
        from sgp4.api import Satrec
        norad = omm.get("NORAD_CAT_ID", 0)
        sat_id = sat_label(omm.get("OBJECT_NAME", ""), system, norad)
        n_rad_s = float(omm["MEAN_MOTION"]) * 2.0 * math.pi / 86400.0
        a = (MU_KM / n_rad_s ** 2) ** (1.0 / 3.0) * 1000.0
        super().__init__(sat_id, a, float(omm["ECCENTRICITY"]), float(omm["INCLINATION"]),
                         float(omm["RA_OF_ASC_NODE"]), float(omm["ARG_OF_PERICENTER"]),
                         float(omm["MEAN_ANOMALY"]), system=system)
        self.name = omm.get("OBJECT_NAME", sat_id)
        self.norad = norad
        self._satrec = Satrec()
        omm_mod.initialize(self._satrec, {k: str(v) for k, v in omm.items()})
        self._epoch = epoch_utc
        self._t0 = float(t0)          # sim-vrijeme koje odgovara epohi
        self._elements_epoch = _parse_epoch(omm["EPOCH"])
        self._n = n_rad_s
        self.valid = True
        self.current_vel = np.zeros(3)

    def _state(self, t):
        d = self._epoch + dt.timedelta(seconds=float(t) - self._t0)
        jd, fr = _jd(d)
        err, r, v = self._satrec.sgp4(jd, fr)
        if err != 0:
            return None, None, d
        pos, vel = _teme_to_ecef(r, v, gmst_rad(d))
        return pos, vel, d

    def velocity_at(self, t):
        _, vel, _ = self._state(t)
        return vel if vel is not None else np.zeros(3)

    def update_position(self, t, rng=None, ideal=False):
        pos, vel, d = self._state(t)
        if pos is None:
            self.valid = False             # SGP4 greška (npr. raspad elemenata) — zadrži zadnju
        else:
            self.valid = True
            self.current_pos, self.current_vel = pos, vel

        dt_s = t - self.last_update_time
        if dt_s > 0:
            self.clock_bias, self.clock_drift = simulate_clock_noise(
                dt_s, self.clock_bias, self.clock_drift, self.h0, self.h2, rng=rng, ideal=ideal)
        # ekscentrična anomalija iz srednjeg gibanja (za relativistički član sata)
        M = math.radians(self.m0) + self._n * (d - self._elements_epoch).total_seconds()
        E = M
        for _ in range(8):
            E = E - (E - self.e * math.sin(E) - M) / (1.0 - self.e * math.cos(E))
        self.total_bias = self.clock_bias + get_dynamic_relativistic_offset(self.a, self.e, E)
        self.ephemeris_error = evolve_ephemeris_error(
            self.ephemeris_error, dt_s if dt_s > 0 else 0.0, rng=rng, ideal=ideal)
        self.broadcast_pos = self.current_pos + self.ephemeris_error
        if self.user_pos_offset_m:
            rnorm = np.linalg.norm(self.current_pos)
            if rnorm > 0:
                self.broadcast_pos = self.broadcast_pos + (self.current_pos / rnorm) * self.user_pos_offset_m
        self.last_update_time = t
        return self.current_pos

    def track_teme(self, n=72):
        """Jedan ophod u TEME okviru [m] oko trenutka epohe — za crtanje orbite."""
        period = 2.0 * math.pi / self._n
        pts = []
        for k in range(n + 1):
            d = self._epoch + dt.timedelta(seconds=period * k / n)
            jd, fr = _jd(d)
            err, r, _ = self._satrec.sgp4(jd, fr)
            if err == 0:
                pts.append([r[0] * 1000.0, r[1] * 1000.0, r[2] * 1000.0])
        return pts


class RealConstellation:
    """Stvarna GNSS konstelacija za zadanu epohu (zamjena za MultiGNSSConstellation)."""

    mode = "real"

    def __init__(self, epoch="now", rng=None, gp=None, systems=("GPS", "GAL", "GLO", "BDS"), t0=0.0):
        self.rng = rng if rng is not None else np.random.default_rng()
        self.epoch = _parse_epoch(epoch)
        self.t0 = float(t0)           # sim-vrijeme koje odgovara epohi (sesija ne kreće od 0)
        data, origin = gp if gp is not None else load_gp(allow_fetch=False)
        self.origin = origin
        self.fetched_utc = data.get("fetched_utc")
        self.sys_bias = {s: GNSS_SYSTEMS[s]["isb_m"] for s in systems}
        self.satellites = []
        seen = set()
        epochs = []
        for group, sysname in GROUPS.items():
            if sysname not in systems:
                continue
            for omm in data.get("groups", {}).get(group, []):
                try:
                    sat = RealSatellite(omm, sysname, self.epoch, t0=self.t0)
                except (KeyError, ValueError):
                    continue
                if sat.sat_id in seen:                 # dvostruka oznaka -> NORAD sufiks
                    sat.sat_id = f"{sat.sat_id}-{sat.norad}"
                seen.add(sat.sat_id)
                self.satellites.append(sat)
                epochs.append(sat._elements_epoch)
        self.elements_epoch_min = min(epochs) if epochs else None
        self.elements_epoch_max = max(epochs) if epochs else None

    def utc_at(self, t):
        return self.epoch + dt.timedelta(seconds=float(t) - self.t0)

    def gmst(self, t):
        return gmst_rad(self.utc_at(t))

    def gps_tod(self, t):
        """GPS vrijeme dana [s] (za Klobuchar ionosferu)."""
        d = self.utc_at(t)
        return (d.hour * 3600 + d.minute * 60 + d.second + d.microsecond * 1e-6 + GPS_UTC_LEAP_S) % 86400.0

    def elements_age_days(self):
        if self.elements_epoch_max is None:
            return None
        return (self.epoch - self.elements_epoch_max).total_seconds() / 86400.0

    def update_all(self, t, ideal=False):
        positions = {}
        for sat in self.satellites:
            positions[sat.sat_id] = sat.update_position(t, rng=self.rng, ideal=ideal)
        return positions

    def tracks(self, n=72):
        return [{"id": s.sat_id, "system": s.system, "pts": s.track_teme(n)} for s in self.satellites]

    def info(self, t=0.0):
        age = self.elements_age_days()
        return {
            "mode": "real", "origin": self.origin, "fetched_utc": self.fetched_utc,
            "epoch_utc": self.epoch.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "utc": self.utc_at(t).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gmst_rad": self.gmst(t),
            "elements_age_days": age,
            "counts": {s: sum(1 for x in self.satellites if x.system == s) for s in GROUPS.values()},
        }
