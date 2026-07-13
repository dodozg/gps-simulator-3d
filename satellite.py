import numpy as np
from physics_engine import calculate_orbital_position, R_EARTH, get_relativistic_drift_rate, simulate_clock_noise, generate_ephemeris_error, get_dynamic_relativistic_offset
import signal_processing

class Satellite:
    def __init__(self, sat_id, a, e, i, lan, w, m0):
        self.sat_id = sat_id
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

    def update_position(self, t):
        self.current_pos, E = calculate_orbital_position(
            self.a, self.e, self.i, self.lan, self.w, self.m0, t
        )
        
        dt = t - self.last_update_time
        if dt > 0:
            # Update clock offset: offset = drift_rate * time + noise
            self.clock_bias, self.clock_drift = simulate_clock_noise(
                dt, self.clock_bias, self.clock_drift, self.h0, self.h2
            )
            
        dyn_rel = get_dynamic_relativistic_offset(self.a, self.e, E)
        self.total_bias = self.clock_bias + dyn_rel
        
        # Prijemnik dobiva ephemeris s malom pogreškom
        self.broadcast_pos = self.current_pos + generate_ephemeris_error()
        self.last_update_time = t
        
        return self.current_pos

    def get_signal(self, system_time):
        """
        Emits two signals (L1 and L2) containing the satellite's position, time, and PRN codes.
        """
        sat_time = system_time + self.total_bias
        
        # Ako je satelit kompromitiran (RAIM test) i prošlo je malo vremena (da EKF konvergira)
        if self.is_spoofed and system_time > 200.0:
            sat_time += 2e-5 # 6 kilometara lažne udaljenosti!
            
        return {
            'id': self.sat_id,
            'pos': self.current_pos.copy(), # Stvarna pozicija za fiziku kanala
            'broadcast_pos': self.broadcast_pos.copy(), # Ono što prijemnik misli da je pozicija
            'time': sat_time,
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
    def __init__(self, t_total=24, p_planes=6, f_factor=1, alt=20200000.0, inc=55.0):
        """
        Initializes a Walker Delta constellation (T/P/F).
        Default is GPS-like: 24/6/1, 20,200km altitude, 55 deg inclination.
        """
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
            positions[sat.sat_id] = sat.update_position(t)
        return positions
