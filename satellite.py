import numpy as np
from physics_engine import calculate_orbital_position, R_EARTH, get_relativistic_drift_rate, simulate_clock_noise, generate_ephemeris_error, get_dynamic_relativistic_offset, C
import signal_processing

class Satellite:
    def __init__(self, sat_id, a, e, i, lan, w, m0, system="GPS"):
        self.sat_id = sat_id
        self.system = system          # GPS / GAL / GLO / BDS (za multi-GNSS, #6)
        self.a = a
        self.e = e
        self.i = i
        self.lan = lan
        self.w = w
        self.m0 = m0
        self.current_pos = np.array([0.0, 0.0, 0.0])
        # Za satelite (Rubidijum/Cezijum oscilatori), Allan variance parametri su jako mali
        self.h0 = 1e-22 # White noise
        self.h2 = 1e-26 # Random walk
        
        self.is_spoofed = False # RAIM testing flag
        
        self.clock_bias = 0.0 # Stvarni offset [s] (hardverski)
        self.total_bias = 0.0 # Uključuje dinamičku relativnost
        self.clock_drift = get_relativistic_drift_rate(self.a) # Početni drift uključuje relativnost
        self.last_update_time = 0.0
        
        # Stvarna i "broadcasted" (objavljena) pozicija
        self.broadcast_pos = np.array([0.0, 0.0, 0.0])

        # Fizički simulirani signali za dvije frekvencije
        self.prn_code_l1 = signal_processing.generate_prn(self.sat_id + "_L1")
        self.prn_code_l2 = signal_processing.generate_prn(self.sat_id + "_L2")

    def update_position(self, t, rng=None):
        self.current_pos, E = calculate_orbital_position(
            self.a, self.e, self.i, self.lan, self.w, self.m0, t
        )

        dt = t - self.last_update_time
        if dt > 0:
            # Update clock offset: offset = drift_rate * time + noise
            self.clock_bias, self.clock_drift = simulate_clock_noise(
                dt, self.clock_bias, self.clock_drift, self.h0, self.h2, rng=rng
            )

        dyn_rel = get_dynamic_relativistic_offset(self.a, self.e, E)
        self.total_bias = self.clock_bias + dyn_rel

        # Prijemnik dobiva ephemeris s malom pogreškom
        self.broadcast_pos = self.current_pos + generate_ephemeris_error(rng=rng)
        self.last_update_time = t

        return self.current_pos

    def get_signal(self, system_time):
        """
        Emits two signals (L1 and L2) containing the satellite's position, time, and PRN codes.
        """
        sat_time = system_time + self.total_bias

        # STVARNA satelitska pogreška sata pretvorena u metre (ulazi u pseudoudaljenost).
        # Ovo je fizička greška koju prijemnik VIDI u mjerenju.
        sat_clock_error_m = self.total_bias * C

        # BROADCAST korekcija sata: ono što bi navigacijska poruka (af0/af1 + relativistički
        # član) prenijela pa prijemnik od toga oduzme. Za ispravan satelit modeliramo cijeli
        # poznati bias -> net efekt ~0 (kao u stvarnom GPS-u). Spoof NIJE u broadcast poruci.
        broadcast_clock_m = self.total_bias * C

        # Ako je satelit kompromitiran (RAIM test) i prošlo je malo vremena (da EKF konvergira)
        if self.is_spoofed and system_time > 200.0:
            sat_time += 2e-5           # 6 km lažne udaljenosti (za prikaz u sat_time)
            sat_clock_error_m += 6000.0 # ...ista greška ubrizgana u stvarno mjerenje (bez broadcast korekcije!)

        return {
            'id': self.sat_id,
            'pos': self.current_pos.copy(), # Stvarna pozicija za fiziku kanala
            'broadcast_pos': self.broadcast_pos.copy(), # Ono što prijemnik misli da je pozicija
            'time': sat_time,
            'sat_clock_m': sat_clock_error_m,       # injektirana greška satelitskog sata [m]
            'broadcast_clock_m': broadcast_clock_m, # korekcija koju prijemnik primjenjuje [m]
            'l1': {
                'freq': 1575.42e6,
                'prn': self.prn_code_l1
            },
            'l2': {
                'freq': 1227.60e6,
                'prn': self.prn_code_l2
            }
        }


class WalkerDeltaConstellation:
    def __init__(self, t_total=24, p_planes=6, f_factor=1, alt=20200000.0, inc=55.0, rng=None):
        """
        Initializes a Walker Delta constellation (T/P/F).
        Default is GPS-like: 24/6/1, 20,200km altitude, 55 deg inclination.
        rng: np.random.Generator koji dijele svi izvori šuma (None -> default_rng).
        """
        self.rng = rng if rng is not None else np.random.default_rng()
        self.satellites = []
        self.a = R_EARTH + alt
        self.e = 0.015  # Ekscentrična orbita za Phase 6
        self.i = inc
        self.w = 45.0  # Argument perigeja
        
        sats_per_plane = t_total // p_planes
        
        for p in range(p_planes):
            lan = p * (360.0 / p_planes)
            for s in range(sats_per_plane):
                # Phasing: F * 360 / T
                m0 = s * (360.0 / sats_per_plane) + p * (f_factor * 360.0 / t_total)
                sat_id = f"SAT_{p}_{s}"
                self.satellites.append(Satellite(sat_id, self.a, self.e, self.i, lan, self.w, m0))

        # RAIM: Namjerno kvarimo prvi satelit
        if len(self.satellites) > 0:
            self.satellites[0].is_spoofed = True

    def update_all(self, t):
        positions = {}
        for sat in self.satellites:
            positions[sat.sat_id] = sat.update_position(t, rng=self.rng)
        return positions


# Realni orbitalni parametri po sustavu + tipični inter-system bias (ISB) u
# metrima (GPS = referenca 0). ISB nastaje jer svaki sustav ima svoju vremensku
# skalu; prijemnik ga mora procijeniti kao dodatno stanje (vidi multignss.py).
GNSS_SYSTEMS = {
    "GPS": dict(t=24, p=6, f=1, alt=20200e3, inc=55.0, isb_m=0.0),
    "GAL": dict(t=24, p=3, f=1, alt=23222e3, inc=56.0, isb_m=12.5),   # Galileo
    "GLO": dict(t=24, p=3, f=1, alt=19100e3, inc=64.8, isb_m=-8.0),   # GLONASS
    "BDS": dict(t=24, p=3, f=1, alt=21500e3, inc=55.0, isb_m=20.0),   # BeiDou (MEO)
}


class MultiGNSSConstellation:
    """Više GNSS konstelacija (GPS/Galileo/GLONASS/BeiDou) s inter-system biasom.

    Svaki sustav je zasebna Walker-Delta konstelacija sa svojim parametrima i
    konstantnim ISB-om. Sateliti su označeni `.system`, a `sys_bias` drži pravi
    ISB po sustavu (istina koju solver treba rekonstruirati).
    """

    def __init__(self, systems=("GPS", "GAL", "GLO", "BDS"), rng=None):
        self.rng = rng if rng is not None else np.random.default_rng()
        self.satellites = []
        self.sys_bias = {}
        for sysname in systems:
            cfg = GNSS_SYSTEMS[sysname]
            self.sys_bias[sysname] = cfg["isb_m"]
            a = R_EARTH + cfg["alt"]
            sats_per_plane = cfg["t"] // cfg["p"]
            for p in range(cfg["p"]):
                lan = p * (360.0 / cfg["p"])
                for s in range(sats_per_plane):
                    m0 = s * (360.0 / sats_per_plane) + p * (cfg["f"] * 360.0 / cfg["t"])
                    sat_id = f"{sysname}_{p}_{s}"
                    self.satellites.append(
                        Satellite(sat_id, a, 0.001, cfg["inc"], lan, 45.0, m0, system=sysname)
                    )

    def update_all(self, t):
        positions = {}
        for sat in self.satellites:
            positions[sat.sat_id] = sat.update_position(t, rng=self.rng)
        return positions
