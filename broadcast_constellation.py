"""Konstelacija iz PRAVIH broadcast efemerida (RINEX nav) — zamjena za Walker-Delta.

`BroadcastConstellation` ima isto sučelje kao `satellite.MultiGNSSConstellation`
(`.satellites`, `.update_all(t, ideal)`, `.rng`, `.sys_bias`), a svaki
`BroadcastSatellite` ono što mjerni model (`measurement.MeasurementModel`) i
serijalizacija (`web/backend/serialize.py`) čitaju sa `satellite.Satellite`:
`sat_id`, `system`, `current_pos`, `broadcast_pos`, `enabled`, `is_spoofed`,
`user_clock_offset_m`, `user_pos_offset_m`, `a/e/i/lan/w` (iz efemeride, za
prikaz), `get_signal(t)` i `update_position(t, rng, ideal)`.

Vrijeme simulacije `t` [s] mjeri se od `start` (GPS sekunde, vidi
`rinex.gps_seconds`), pa simulator prikazuje STVARNE položaje GPS satelita za
odabrani datum/vrijeme.

Model "istine" vs. "broadcast":
  * prava pozicija (`current_pos`) = IS-GPS-200 pozicija iz efemeride;
  * objavljena (`broadcast_pos`) = prava + sporo-promjenjiva OU greška
    (`physics_engine.evolve_ephemeris_error`, ~1.5 m po osi), kao kod
    `Satellite` — u `ideal` modu greška je 0;
  * sat satelita = broadcast polinom (af0/af1/af2 + relativistički član); broadcast
    korekcija ga poništava (net 0), korisnički kvar sata / spoof ostaju rezidual.

Kako spojiti u živu sesiju (web/backend/sim_session.py — NIJE spojeno ovdje):

    import rinex
    from broadcast_constellation import BroadcastConstellation
    nav = rinex.read_nav("tests/data/07590920.05n")
    start = rinex.gps_seconds(2005, 4, 2, 0, 0, 0)
    self.constellation = BroadcastConstellation(nav, start, rng=self.rng)
    # Klobuchar: doba dana iz pravog GPS vremena (MeasurementModel dodaje sim t)
    self.receiver.iono_tow0 = self.constellation.start_tow % 86400.0

  - `SimSession._build` umjesto `MultiGNSSConstellation(rng=self.rng)`; ostatak
    (enabled/systems_on, update_all, get_signal) radi bez promjene jer je
    sučelje isto. Sustav je samo "GPS" (ostali toggleovi nemaju satelite).
  - Editor satelita: `clock_offset_m` i `pos_offset_m` rade; `alt_km/inc_deg/
    lan_deg/ecc` se upisuju u atribute, ali NE mijenjaju putanju (određuje je
    efemerida) — UI bi ih za ovu konstelaciju trebao zaključati.
  - Za datum izvan pokrivenosti nav datoteke satelit postaje `valid=False`
    (pozicija ostaje zadnja poznata) — mjerni model ga i dalje vidi, pa sesija
    treba filtrirati `valid` (npr. `enabled = enabled and valid`).
"""
from __future__ import annotations

import numpy as np

import signal_processing
from ephemeris import (C_LIGHT, MAX_DTOE, sat_clock, sat_position,
                       select_ephemeris)
from physics_engine import evolve_ephemeris_error
from rinex import gps_week_tow

L1_HZ = 1575.42e6
L2_HZ = 1227.60e6


class BroadcastSatellite:
    def __init__(self, sat_id, ephemerides, start, system="GPS"):
        self.sat_id = sat_id
        self.system = system
        self.ephemerides = list(ephemerides)
        self.start = float(start)
        self.enabled = True
        self.valid = True                # ima li važeću efemeridu u trenutku t
        self.is_spoofed = False
        self.user_clock_offset_m = 0.0
        self.user_pos_offset_m = 0.0
        self.current_pos = np.zeros(3)
        self.broadcast_pos = np.zeros(3)
        self.ephemeris_error = None
        self.total_bias = 0.0            # [s] sat satelita (af + relativnost)
        self.last_update_time = 0.0
        self.eph = None
        self._select(self.start)
        # PRN kodovi istim mehanizmom kao `Satellite` (deterministički po sat_id)
        self.prn_code_l1 = signal_processing.generate_prn(self.sat_id + "_L1")
        self.prn_code_l2 = signal_processing.generate_prn(self.sat_id + "_L2")

    # Keplerovi elementi samo za PRIKAZ/serijalizaciju (putanju određuje efemerida).
    def _sync_elements(self):
        e = self.eph
        self.a = e.sqrt_a ** 2
        self.e = e.e
        self.i = float(np.degrees(e.i0))
        self.lan = float(np.degrees(e.omega0)) % 360.0
        self.w = float(np.degrees(e.omega)) % 360.0
        self.m0 = float(np.degrees(e.m0)) % 360.0

    def _select(self, gps_t):
        cur = self.eph
        if cur is not None and abs(gps_t - cur.toe) <= MAX_DTOE / 2:
            return
        eph = select_ephemeris(self.ephemerides, gps_t)
        self.valid = eph is not None
        if eph is None:
            if cur is None:            # bez ijedne važeće: uzmi najbližu (samo za prikaz)
                eph = min(self.ephemerides, key=lambda x: abs(gps_t - x.toe))
            else:
                return
        if eph is not cur:
            self.eph = eph
            self._sync_elements()

    def update_position(self, t, rng=None, ideal=False):
        gps_t = self.start + float(t)
        self._select(gps_t)
        self.current_pos, _ = sat_position(self.eph, gps_t)
        self.total_bias = sat_clock(self.eph, gps_t)
        dt = t - self.last_update_time
        self.ephemeris_error = evolve_ephemeris_error(
            self.ephemeris_error, dt if dt > 0 else 0.0, rng=rng, ideal=ideal)
        self.broadcast_pos = self.current_pos + self.ephemeris_error
        if self.user_pos_offset_m:
            rn = np.linalg.norm(self.current_pos)
            if rn > 0:
                self.broadcast_pos = self.broadcast_pos + (self.current_pos / rn) * self.user_pos_offset_m
        self.last_update_time = t
        return self.current_pos

    def get_signal(self, system_time):
        """Isti oblik kao `satellite.Satellite.get_signal` (vidi measurement._finalize)."""
        sat_clock_m = self.total_bias * C_LIGHT
        broadcast_clock_m = self.total_bias * C_LIGHT
        if self.is_spoofed and system_time > 200.0:
            sat_clock_m += 6000.0
        sat_clock_m += self.user_clock_offset_m
        return {
            "id": self.sat_id,
            "pos": self.current_pos.copy(),
            "broadcast_pos": self.broadcast_pos.copy(),
            "time": system_time + self.total_bias,
            "sat_clock_m": sat_clock_m,
            "broadcast_clock_m": broadcast_clock_m,
            "l1": {"freq": L1_HZ, "prn": self.prn_code_l1},
            "l2": {"freq": L2_HZ, "prn": self.prn_code_l2},
        }


class BroadcastConstellation:
    """GPS konstelacija iz RINEX navigacijske datoteke, od GPS trenutka `start`.

    nav: `rinex.RinexNav` (ili put do datoteke). start: GPS sekunde
    (`rinex.gps_seconds(...)`). Uzimaju se sateliti koji u `start` imaju važeću
    (zdravu, |t−toe| ≤ 2 h) efemeridu; `include_all=True` uzima sve iz datoteke.
    """

    def __init__(self, nav, start, rng=None, include_all=False):
        if isinstance(nav, str):
            import rinex
            nav = rinex.read_nav(nav)
        self.nav = nav
        self.start = float(start)
        self.start_week, self.start_tow = gps_week_tow(self.start)
        self.rng = rng if rng is not None else np.random.default_rng()
        self.sys_bias = {"GPS": 0.0}
        self.satellites = []
        for prn in sorted(nav.ephemerides):
            ephs = nav.ephemerides[prn]
            if not include_all and select_ephemeris(ephs, self.start) is None:
                continue
            self.satellites.append(BroadcastSatellite(prn, ephs, self.start))
        if not self.satellites:
            raise ValueError("Nav datoteka nema važećih GPS efemerida za zadani trenutak")

    def update_all(self, t, ideal=False):
        positions = {}
        for sat in self.satellites:
            positions[sat.sat_id] = sat.update_position(t, rng=self.rng, ideal=ideal)
        return positions
