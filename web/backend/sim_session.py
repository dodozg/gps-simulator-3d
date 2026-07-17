"""Živa simulacijska sesija — tanki omotač oko konstelacije + Receivera.

Drži stanje jednog "prijemnika u svijetu" i napreduje ga po epohama, headless i
serijalizabilno. Kvarove (spoofing/jamming) ubrizgava na razinu mjerenja prije
rješavanja — isti obrazac kao `scenario.run_scenario`. Deterministički:
konstelacija i prijemnik dijele isti seedani `np.random.default_rng`.
"""
from types import SimpleNamespace

import numpy as np

from satellite import MultiGNSSConstellation, GNSS_SYSTEMS
from physics_engine import R_EARTH
from receiver import Receiver
from utils import lla_to_ecef, ecef_to_lla
import terrain
from scenario import build_attack

MAX_SIM_DT = 5.0          # gornja granica koraka sim-vremena [s] (stabilnost)
DEFAULT_SYSTEMS_ON = ("GPS",)   # ostale konstelacije korisnik pali iz UI-ja


class SimSession:
    def __init__(self, seed=1234):
        self.seed = seed
        self._build()

    def _build(self):
        self.rng = np.random.default_rng(self.seed)
        # Sve GNSS konstelacije (GPS/Galileo/GLONASS/BeiDou); koje su aktivne u
        # rješenju kontrolira `systems_on` + `enabled` po satelitu (web toggle).
        self.constellation = MultiGNSSConstellation(rng=self.rng)
        self.systems_on = set(DEFAULT_SYSTEMS_ON)
        for s in self.constellation.satellites:
            s.is_spoofed = False              # kvarove definira sesija, ne default
            s.enabled = s.system in self.systems_on
        self.receiver = Receiver(np.zeros(3), rng=self.rng)
        self.sim_time = 0.0
        self.time_scale = 100.0
        self.playing = False
        self.kinematic = False
        self.kinematic_velocity = np.array([100.0, 50.0, 0.0])
        self.gt_pos = None                    # ECEF prave pozicije (None = nije postavljen)
        self.attack = None                    # spec dict ili None
        self._attack_obj = None
        # zadnji rezultat (za serijalizaciju)
        self.calc_pos = None
        self.gdop = None
        self.tracked_ids = set()

    # --- kontrole ---------------------------------------------------------
    def set_receiver(self, lat, lon, alt=None):
        # alt=None -> postavi na STVARNU nadmorsku visinu terena na toj točki
        # (DEM), umjesto fiksnih 100 m. Ocean = 0 m.
        if alt is None:
            alt = float(terrain.elevation(lat, lon))
        self.gt_pos = np.array(lla_to_ecef(lat, lon, alt))
        self.receiver.set_position(self.gt_pos)
        self.receiver.reset()
        self.calc_pos = None
        self.tracked_ids = set()

    def set_playing(self, on):
        self.playing = bool(on)

    def set_time_scale(self, ts):
        self.time_scale = float(np.clip(ts, 1.0, 2000.0))

    def set_kinematic(self, on):
        self.kinematic = bool(on)

    def set_raim(self, on):
        self.receiver.raim_enabled = bool(on)

    def set_system_enabled(self, system, on):
        """Upali/ugasi cijelu konstelaciju (svi njeni sateliti)."""
        on = bool(on)
        if system not in GNSS_SYSTEMS:
            return
        if on:
            self.systems_on.add(system)
        else:
            self.systems_on.discard(system)
        for s in self.constellation.satellites:
            if s.system == system:
                s.enabled = on

    def set_sat_enabled(self, sat_id, on):
        """Upali/ugasi jedan satelit (fina kontrola preko tablice)."""
        for s in self.constellation.satellites:
            if s.sat_id == sat_id:
                s.enabled = bool(on)
                return

    def set_sat_param(self, sat_id, param, value):
        """Editor satelita: kvar sata / orbita. param: clock_offset_m | alt_km | inc_deg."""
        v = float(value)
        for s in self.constellation.satellites:
            if s.sat_id == sat_id:
                if param == "clock_offset_m":
                    s.user_clock_offset_m = v
                elif param == "alt_km":
                    s.a = R_EARTH + max(v, 100.0) * 1000.0   # sanity: iznad površine
                elif param == "inc_deg":
                    s.i = float(np.clip(v, 0.0, 90.0))
                elif param == "lan_deg":
                    s.lan = float(v) % 360.0   # rektascenzija uzlaznog čvora (rotacija ravnine)
                return

    def set_iono_tow0(self, tow):
        self.receiver.iono_tow0 = float(tow) % 86400.0

    def set_attack(self, spec):
        if not spec:
            self.attack = None
            self._attack_obj = None
            return
        s = {"type": spec} if isinstance(spec, str) else dict(spec)
        # Živa sesija: zadani prozor napada (60-240 s) je apsolutno sim-vrijeme,
        # a sesija tipično već ima veliki sim_time -> napad se ne bi nikad
        # aktivirao. Zato prozor sidrimo relativno na SADA ako nije zadan.
        s.setdefault("start", self.sim_time + 3.0)
        s.setdefault("end", float(s["start"]) + 300.0)
        self._attack_obj = build_attack(s)
        self.attack = s

    def attack_active(self):
        a = self._attack_obj
        if a is None:
            return False
        return getattr(a, "start", 0.0) <= self.sim_time <= getattr(a, "end", 0.0)

    def attack_overlay(self):
        """Prostorni prikaz napada za globus (None ako nema/nije primjenjivo).

        - coordinated: točka kamo napadač povlači rješenje (spoof pull vektor).
        - jamming: simbolički radijus uskraćivanja oko prijemnika.
        """
        a = self._attack_obj
        if a is None or self.gt_pos is None:
            return None
        kind = self.attack.get("type") if self.attack else None
        act = self.attack_active()
        if kind == "coordinated":
            tgt = a.target_ecef(self.gt_pos)
            return {"type": "coordinated", "active": act,
                    "target_ecef": [float(v) for v in tgt]}
        if kind == "jamming":
            return {"type": "jamming", "active": act, "radius_m": 25000.0}
        return {"type": kind, "active": act}

    def reset(self):
        self._build()

    # --- korak simulacije -------------------------------------------------
    def advance(self, sim_dt):
        """Napreduj sim-vrijeme za `sim_dt` sekundi i odvrti jednu epohu."""
        sim_dt = float(np.clip(sim_dt, 0.0, MAX_SIM_DT))
        self.sim_time += sim_dt
        t = self.sim_time

        self.constellation.update_all(t)

        # kinematički način: pomakni pravu poziciju i drži je iznad terena
        if self.kinematic and self.gt_pos is not None:
            self.gt_pos = self.gt_pos + self.kinematic_velocity * sim_dt
            lat, lon, _ = ecef_to_lla(*self.gt_pos)
            h = terrain.elevation(lat, lon) + 500.0
            self.gt_pos = np.array(lla_to_ecef(lat, lon, h))
            self.receiver.set_position(self.gt_pos)

        # U rješenje ulaze samo UPALJENI sateliti; ugašeni se i dalje pomiču
        # (update_all) i crtaju, ali ih prijemnik ne prima.
        enabled = SimpleNamespace(
            satellites=[s for s in self.constellation.satellites if s.enabled])
        self.receiver.receive_signals(enabled, t)
        if self._attack_obj is not None and self.gt_pos is not None:
            self._attack_obj.apply(self.receiver.received_signals, t, self.gt_pos, self.rng)

        self.tracked_ids = {s['sat_id'] for s in self.receiver.received_signals}

        if self.gt_pos is not None:
            self.calc_pos, self.gdop = self.receiver.solve_position()
        return self
