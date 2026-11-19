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
from spoofing import Jamming
from rtk import LiveRTK
from utils import WGS84_A, WGS84_B, WGS84_E2

# Gornja granica koraka sim-vremena po epohi [s]. Jedna epoha košta ~60-130 ms CPU-a
# (FFT kanal po satelitu), pa se pri 10 Hz streamu ostvarivo ubrzanje ≈ MAX_SIM_DT /
# trajanje_ticka. S 5 s je strop bio ~×30 dok je klizač nudio ×1000; 30 s daje
# ~×150-250, a EKF (Q skaliran s dt) i orbite ostaju stabilni (vidi test). Stvarno
# ostvareno ubrzanje se mjeri i šalje u frameu (`time_scale_actual`).
MAX_SIM_DT = 30.0
DEFAULT_SYSTEMS_ON = ("GPS",)   # ostale konstelacije korisnik pali iz UI-ja

# --- živi RTK (vidi rtk.LiveRTK) ---------------------------------------------
# Automatska baza ("najbliža CORS stanica") stoji par km od rovera. Kad se rover u
# kinematici previše udalji, prebacujemo se na novu bližu bazu (kao u mreži
# referentnih stanica) — to znači NOVE neodređenosti, tj. ponovnu inicijalizaciju.
# Korisnički postavljena baza se nikad sama ne miče (RTK slabi s duljinom baze).
RTK_AUTO_BASE_OFFSET_M = 4000.0
RTK_AUTO_BASE_SWITCH_M = 20000.0
RTK_BASE_ANTENNA_M = 2.0           # antena baze iznad terena


def _ecef_to_lla_vec(p):
    """Vektorizirani ECEF -> (lat°, lon°, alt) (Bowring, kao utils.ecef_to_lla)."""
    x, y, z = p[..., 0], p[..., 1], p[..., 2]
    ep2 = (WGS84_A ** 2 - WGS84_B ** 2) / WGS84_B ** 2
    lon = np.arctan2(y, x)
    r = np.maximum(np.hypot(x, y), 1e-6)
    th = np.arctan2(z * WGS84_A, r * WGS84_B)
    lat = np.arctan2(z + ep2 * WGS84_B * np.sin(th) ** 3, r - WGS84_E2 * WGS84_A * np.cos(th) ** 3)
    n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
    return np.degrees(lat), np.degrees(lon), r / np.cos(lat) - n


def _los_clear(rover, sat_positions):
    """Za svaki satelit: je li put rover->satelit slobodan od terena (do 60 km).

    Isto uzorkovanje kao `measurement.check_los`, ali vektorizirano za sve
    satelite odjednom (jedan poziv DEM-a), da RTK ostane jeftin."""
    sp = np.asarray(sat_positions, dtype=float)
    v = sp - rover
    u = v / np.linalg.norm(v, axis=1, keepdims=True)
    d = np.arange(2000.0, 60000.0, 2000.0)
    pts = rover + u[:, None, :] * d[None, :, None]          # (n_sat, n_uzoraka, 3)
    lat, lon, alt = _ecef_to_lla_vec(pts)
    h = terrain.elevation_array(lat.ravel(), lon.ravel()).reshape(lat.shape)
    return list(np.all(alt >= h, axis=1))


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
        self.time_scale_actual = 0.0          # izmjereno ubrzanje (postavlja SimRunner)
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
        # živi carrier-phase RTK (isključen dok ga korisnik ne upali)
        self.rtk = LiveRTK(seed=self.seed + 7)

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
        self._rtk_relocated()

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
                elif param == "ecc":
                    s.e = float(np.clip(v, 0.0, 0.3))   # ekscentricitet (0 = kružna)
                elif param == "pos_offset_m":
                    s.user_pos_offset_m = float(max(v, 0.0))   # spoof pozicije (radijalni pomak)
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
        # aktivirao. Zato rampu sidrimo relativno na SADA ako nije zadana. Nakon
        # rampe napad djeluje punom snagom dok ga korisnik ne ugasi (stop=None),
        # pa je prikaz (attack_active/overlay) uvijek usklađen sa stvarnim učinkom.
        s.setdefault("start", self.sim_time + 3.0)
        s.setdefault("end", float(s["start"]) + 300.0)
        self._attack_obj = build_attack(s)
        self.attack = s

    def attack_active(self):
        """Djeluje li napad SADA — isti kriterij koji koristi i apply() napada."""
        a = self._attack_obj
        return bool(a is not None and a.is_active(self.sim_time))

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

    # --- živi RTK ---------------------------------------------------------
    def _auto_base_ecef(self):
        """Automatska baza RTK_AUTO_BASE_OFFSET_M od rovera (u kinematici ISPRED njega)."""
        lat, lon, _ = ecef_to_lla(*self.gt_pos)
        la, lo = np.radians(lat), np.radians(lon)
        east = np.array([-np.sin(lo), np.cos(lo), 0.0])
        north = np.array([-np.sin(la) * np.cos(lo), -np.sin(la) * np.sin(lo), np.cos(la)])
        if self.kinematic:
            v = self.kinematic_velocity
            ve, vn = float(np.dot(v, east)), float(np.dot(v, north))
            az = np.arctan2(ve, vn) if (ve or vn) else np.radians(60.0)
        else:
            az = np.radians(60.0)              # ~SI-ISI od rovera
        d = RTK_AUTO_BASE_OFFSET_M
        dn, de = d * np.cos(az), d * np.sin(az)
        blat = lat + np.degrees(dn / 6378137.0)
        blon = lon + np.degrees(de / (6378137.0 * max(np.cos(la), 1e-6)))
        return self._base_ecef(blat, blon, None)

    @staticmethod
    def _base_ecef(lat, lon, alt):
        if alt is None:
            alt = max(float(terrain.elevation(lat, lon)), 0.0) + RTK_BASE_ANTENNA_M
        return np.array(lla_to_ecef(lat, lon, alt))

    def _rtk_relocated(self):
        """Rover (pre)mješten: auto baza ide za njim; RTK kreće ispočetka."""
        if self.gt_pos is None:
            return
        if self.rtk.base is None or self.rtk.base_auto:
            self.rtk.set_base(self._auto_base_ecef(), auto=True, t=self.sim_time)
        else:
            self.rtk.restart(self.sim_time)

    def set_rtk(self, on):
        on = bool(on)
        if on and not self.rtk.enabled:
            self.rtk.enabled = True
            self._rtk_relocated()             # svjež start (TTF se mjeri od uključenja)
        elif not on:
            self.rtk.enabled = False

    def set_base(self, lat=None, lon=None, alt=None):
        """Postavi RTK bazu na (lat, lon[, alt]); lat=None -> automatska baza."""
        if lat is None or lon is None:
            if self.rtk.base_auto and self.rtk.base is not None:
                return                         # već automatska -> ne resetiraj RTK
            self.rtk.base_auto = True
            self.rtk.base = None
            self._rtk_relocated()
            return
        ecef = self._base_ecef(float(lat), float(lon), alt)
        if (not self.rtk.base_auto and self.rtk.base is not None
                and np.linalg.norm(ecef - self.rtk.base) < 1.0):
            return                             # ista baza (npr. ponovno spajanje klijenta)
        self.rtk.set_base(ecef, auto=False, t=self.sim_time)

    def _rtk_jam_filter(self, sats):
        """Ometanje (jamming) gasi i fazno praćenje: vrati sat_id koji ga prežive."""
        a = self._attack_obj
        if not isinstance(a, Jamming) or not a.is_active(self.sim_time):
            return None
        sigs = [{"sat_id": sid, "sat_pos": pos, "pseudorange": 0.0} for sid, pos in sats]
        a.apply(sigs, self.sim_time, self.gt_pos, self.rtk.rng)
        return {g["sat_id"] for g in sigs}

    def _rtk_step(self, enabled_sats):
        rtk = self.rtk
        bl = rtk.baseline_m(self.gt_pos)
        if rtk.base_auto and bl is not None and bl > RTK_AUTO_BASE_SWITCH_M:
            rtk.set_base(self._auto_base_ecef(), auto=True, t=self.sim_time)
            rtk.base_switches += 1

        def jam_ok(ss):
            keep = self._rtk_jam_filter(ss)
            return {sid for sid, _ in ss} if keep is None else keep

        rtk.step(self.sim_time, enabled_sats, self.gt_pos, self.kinematic,
                 los_ok=lambda sp: _los_clear(self.gt_pos, sp), jam_ok=jam_ok)

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
            if self.rtk.enabled:
                self._rtk_step(enabled.satellites)
        return self
