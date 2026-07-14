"""Živa simulacijska sesija — tanki omotač oko konstelacije + Receivera.

Drži stanje jednog "prijemnika u svijetu" i napreduje ga po epohama, jednako kao
`main.py:_step`, ali headless i serijalizabilno. Kvarove (spoofing/jamming)
ubrizgava na razinu mjerenja prije rješavanja — isti obrazac kao
`scenario.run_scenario`. Deterministički: konstelacija i prijemnik dijele isti
seedani `np.random.default_rng`.
"""
import numpy as np

from satellite import WalkerDeltaConstellation
from receiver import Receiver
from utils import lla_to_ecef, ecef_to_lla
import terrain
from scenario import build_attack

MAX_SIM_DT = 5.0          # gornja granica koraka sim-vremena [s] (stabilnost)


class SimSession:
    def __init__(self, seed=1234):
        self.seed = seed
        self._build()

    def _build(self):
        self.rng = np.random.default_rng(self.seed)
        self.constellation = WalkerDeltaConstellation(rng=self.rng)
        for s in self.constellation.satellites:
            s.is_spoofed = False              # kvarove definira sesija, ne default
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
    def set_receiver(self, lat, lon, alt):
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

    def set_iono_tow0(self, tow):
        self.receiver.iono_tow0 = float(tow) % 86400.0

    def set_attack(self, spec):
        self.attack = spec
        self._attack_obj = build_attack(spec) if spec else None

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

        self.receiver.receive_signals(self.constellation, t)
        if self._attack_obj is not None and self.gt_pos is not None:
            self._attack_obj.apply(self.receiver.received_signals, t, self.gt_pos, self.rng)

        self.tracked_ids = {s['sat_id'] for s in self.receiver.received_signals}

        if self.gt_pos is not None:
            self.calc_pos, self.gdop = self.receiver.solve_position()
        return self
