import numpy as np
from physics_engine import C, calculate_ionospheric_delay, calculate_tropospheric_delay, calculate_sagnac_correction, simulate_clock_noise, calculate_terrain_elevation, R_EARTH
from utils import ecef_to_lla
import signal_processing

class Receiver:
    def __init__(self, pos=np.array([0.0, 0.0, 0.0])):
        self.pos = pos
        self.clock_bias = 0.0 # [s]
        self.clock_drift = 1e-6 # [s/s] Početni drift za TCXO kvarc oscilator (1 ppm)
        self.h0 = 1e-19 # Allan variance parametri za kvarc
        self.h2 = 1e-20 
        self.last_update_time = 0.0
        self.raim_alarm = ""
        
        # EKF State
        self.ekf_initialized = False
        self.x_ekf = np.zeros(8) # [x, y, z, vx, vy, vz, c*bias, c*drift]
        self.P_ekf = np.eye(8) * 1e6
        self.ekf_last_time = 0.0

    def set_position(self, pos):
        self.pos = pos

    def reset(self):
        self.ekf_initialized = False
        self.x_ekf = np.zeros(8)
        self.P_ekf = np.eye(8) * 1e6
        self.raim_alarm = ""
        self.ekf_last_time = 0.0

    def check_los(self, sat_pos, rec_pos):
        """
        Matematički raycasting: provjerava blokira li teren (planine) putanju signala.
        """
        vec = sat_pos - rec_pos
        dist = np.linalg.norm(vec)
        if dist == 0: return False
        direction = vec / dist
        
        # Uzorkujemo putanju do 60 km udaljenosti
        for d in np.arange(2000, 60000, 2000):
            test_p = rec_pos + direction * d
            lat, lon, alt = ecef_to_lla(test_p[0], test_p[1], test_p[2])
            terrain_h = calculate_terrain_elevation(lat, lon)
            if alt < terrain_h:
                return False # Blokirano terenom!
                
        return True

    def receive_signals(self, constellation, current_time):
        """
        Receives signals from all visible satellites.
        Now simulates physical RF reception, atmospheric delay, and correlation decoding.
        """
        self.received_signals = []
        
        dt = current_time - self.last_update_time
        if dt > 0:
            self.clock_bias, self.clock_drift = simulate_clock_noise(
                dt, self.clock_bias, self.clock_drift, self.h0, self.h2
            )
        self.last_update_time = current_time
        
        # Ako prijemnik još nije postavljen (nalazi se u središtu Zemlje), ne može primati signale
        if np.linalg.norm(self.pos) < 1.0:
            return self.received_signals
            
        visible_signals = []
        
        for sat in constellation.satellites:
            sig = sat.get_signal(current_time)
            
            # 1. Čista geometrijska udaljenost (za potrebe simulacije kanala)
            vec = sig['pos'] - self.pos
            true_dist = np.linalg.norm(vec)
            
            # LOS (Line of Sight) check
            if true_dist == 0:
                continue
            
            sat_dir = vec / true_dist
            rec_dir = self.pos / np.linalg.norm(self.pos)
            elevation = np.arcsin(np.dot(rec_dir, sat_dir))
            
            # Elevation mask: Ignore satellites below ~5 degrees
            if elevation < np.radians(5):
                continue
                
            # LOS Raycasting provjerava planine
            if not self.check_los(sig['pos'], self.pos):
                continue
                
            # 2. Sačuvaj za selekciju
            sig['true_dist'] = true_dist
            visible_signals.append((sat, sig))
            
        # Pametna selekcija najboljih satelita (DOP Optimization)
        selected_pairs = self.select_best_satellites(visible_signals, max_sats=6)
        
        for sat, sig in selected_pairs:
            true_dist = sig['true_dist']
            
            # 3. Atmosfersko kašnjenje
            tropo_delay_meters = calculate_tropospheric_delay(sig['pos'], self.pos)
            
            # L1 Obrada
            iono_delay_l1 = calculate_ionospheric_delay(sig['pos'], self.pos, sig['l1']['freq'])
            rx_signal_l1, int_blocks_l1 = signal_processing.simulate_rf_channel(
                prn=sig['l1']['prn'], distance=true_dist, iono_delay_meters=iono_delay_l1+tropo_delay_meters, snr_db=-10
            )
            local_prn_l1 = signal_processing.generate_prn(sat.sat_id + "_L1")
            measured_pr_l1 = signal_processing.decode_signal(rx_signal_l1, local_prn_l1, int_blocks_l1)
            
            # L2 Obrada
            iono_delay_l2 = calculate_ionospheric_delay(sig['pos'], self.pos, sig['l2']['freq'])
            rx_signal_l2, int_blocks_l2 = signal_processing.simulate_rf_channel(
                prn=sig['l2']['prn'], distance=true_dist, iono_delay_meters=iono_delay_l2+tropo_delay_meters, snr_db=-10
            )
            local_prn_l2 = signal_processing.generate_prn(sat.sat_id + "_L2")
            measured_pr_l2 = signal_processing.decode_signal(rx_signal_l2, local_prn_l2, int_blocks_l2)
            
            # Iono-Free kombinacija
            f1_2 = sig['l1']['freq']**2
            f2_2 = sig['l2']['freq']**2
            iono_free_pr = (f1_2 * measured_pr_l1 - f2_2 * measured_pr_l2) / (f1_2 - f2_2)
            
            # Dodajemo pogrešku sata prijemnika (bias) na kombinaciju
            iono_free_pr += (self.clock_bias * C)
            
            self.received_signals.append({
                'sat_id': sig['id'],
                'sat_pos': sig['pos'],
                'broadcast_pos': sig['broadcast_pos'], # Prijemnik ZNA samo ovu poziciju
                'pseudorange': iono_free_pr,
                'true_dist': true_dist # Spremljeno samo za analizu
            })
            
        return self.received_signals

    def calculate_gdop(self, satellite_pairs):
        H = []
        for sat, sig in satellite_pairs:
            vec = sig['broadcast_pos'] - self.pos
            r = np.linalg.norm(vec)
            if r == 0: r = 1.0
            H.append([vec[0]/r, vec[1]/r, vec[2]/r, 1.0])
        H = np.array(H)
        try:
            cov = np.linalg.inv(H.T @ H)
            return np.sqrt(np.trace(cov))
        except:
            return float('inf')

    def select_best_satellites(self, visible_pairs, max_sats=6):
        """
        DOP Optimization: Bira podgrupu satelita koja minimizira GDOP,
        štedeći procesorsko vrijeme i bateriju prijemnika.
        """
        if len(visible_pairs) <= max_sats:
            return visible_pairs
            
        import random
        best_dop = float('inf')
        best_combo = visible_pairs[:max_sats]
        
        # Testiramo 20 nasumičnih kombinacija (Greedy-Random pristup za brzinu)
        for _ in range(20):
            combo = random.sample(visible_pairs, max_sats)
            dop = self.calculate_gdop(combo)
            if dop < best_dop:
                best_dop = dop
                best_combo = combo
                
        return best_combo

    def solve_position(self, max_iter=10, tolerance=1.0):
        """
        Solves for the receiver position using an Extended Kalman Filter (EKF) with RAIM.
        """
        if len(self.received_signals) < 4:
            return None, None
            
        self.raim_alarm = ""

        current_time = self.last_update_time

        # --- EKF INICIJALIZACIJA (Least Squares) ---
        if not self.ekf_initialized:
            x_ls = np.array([0.0, 0.0, 0.0, 0.0])
            for i in range(max_iter):
                residuals, jacobian = [], []
                for sig in self.received_signals:
                    sat_pos = sig['broadcast_pos']
                    pr = sig['pseudorange']
                    diff = x_ls[:3] - sat_pos
                    r_est = np.linalg.norm(diff)
                    if r_est < 1.0: r_est = 1.0
                    sagnac = calculate_sagnac_correction(sat_pos, x_ls[:3])
                    res = pr - (r_est + x_ls[3] + sagnac)
                    residuals.append(res)
                    jacobian.append([diff[0]/r_est, diff[1]/r_est, diff[2]/r_est, 1.0])
                
                G = np.array(jacobian)
                try:
                    delta_x, _, _, _ = np.linalg.lstsq(G, np.array(residuals), rcond=None)
                except np.linalg.LinAlgError:
                    return None, None
                    
                x_ls += delta_x
                if np.linalg.norm(delta_x[:3]) < tolerance:
                    self.x_ekf[0:3] = x_ls[:3] # Pozicija
                    self.x_ekf[6] = x_ls[3]    # c*bias
                    self.ekf_initialized = True
                    self.ekf_last_time = current_time
                    break
            
            if not self.ekf_initialized:
                return None, None

        # --- EKF PREDVIĐANJE (PREDICT) ---
        dt = current_time - self.ekf_last_time
        if dt <= 0:
            dt = 1e-6 # Sprječavanje dijeljenja nulom
            
        F = np.eye(8)
        F[0, 3] = dt # x += vx * dt
        F[1, 4] = dt # y += vy * dt
        F[2, 5] = dt # z += vz * dt
        F[6, 7] = dt # c*bias += c*drift * dt
        
        # Procesni šum Q (nesigurnost modela)
        # Veći šum znači da filter više "vjeruje" novim mjerenjima nego predviđanju
        q_pos = 0.5
        q_vel = 1.0
        q_bias = 5.0
        q_drift = 1.0
        Q = np.diag([q_pos, q_pos, q_pos, q_vel, q_vel, q_vel, q_bias, q_drift]) * dt
        
        # Predviđanje stanja i kovarijance
        x_pred = F @ self.x_ekf
        P_pred = F @ self.P_ekf @ F.T + Q
        
        # --- EKF AŽURIRANJE (UPDATE) ---
        # Validni signali za H i Z (filtrirani RAIM-om)
        H_valid = []
        Z_valid = []
        h_x_valid = []
        # Prvo izračunamo sve inovacije kako bismo našli medijanu (zajedničku pogrešku sata)
        all_innovations = []
        for sig in self.received_signals:
            sat_pos = sig['broadcast_pos']
            pr = sig['pseudorange']
            
            diff = x_pred[:3] - sat_pos
            r_est = np.linalg.norm(diff)
            if r_est < 1.0: r_est = 1.0
            
            sagnac = calculate_sagnac_correction(sat_pos, x_pred[:3])
            h_x_val = r_est + x_pred[6] + sagnac
            innovation = pr - h_x_val
            all_innovations.append((innovation, h_x_val, diff, r_est))
            
        if len(all_innovations) > 0:
            median_inn = np.median([x[0] for x in all_innovations])
        else:
            median_inn = 0.0

        for i, sig in enumerate(self.received_signals):
            innovation, h_x_val, diff, r_est = all_innovations[i]
            
            # RAIM CHECK: Odbaci samo prave uljeze (udaljene od medijane)
            if self.ekf_initialized and abs(innovation - median_inn) > 1000.0:
                self.raim_alarm = f"RAIM ALARM: Rejected {sig['sat_id']} (Err: {abs(innovation - median_inn):.0f}m)"
                continue
                
            H_row = np.zeros(8)
            H_row[0] = diff[0] / r_est
            H_row[1] = diff[1] / r_est
            H_row[2] = diff[2] / r_est
            H_row[6] = 1.0 # c*bias
            
            H_valid.append(H_row)
            Z_valid.append(sig['pseudorange'])
            h_x_valid.append(h_x_val)
            
        if len(H_valid) < 4:
            return None, None # RAIM odbacio previše satelita
            
        H = np.array(H_valid)
        Z = np.array(Z_valid)
        h_x = np.array(h_x_valid)
        
        # Mjerni šum R (Sada imamo multipath, troposferu, efemeride...)
        # Procjenjujemo da je pogreška pseudoudaljenosti oko 15-30 metara
        R = np.eye(len(H_valid)) * 400.0 # 20m standardna devijacija (20^2 = 400)
        
        # Inovacijska kovarijanca S
        S = H @ P_pred @ H.T + R
        
        # Inovacija (razlika između mjerenog i predviđenog)
        Y = Z - h_x
        
        # Kalman gain K
        try:
            K = P_pred @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return x_pred[:3], None # Fallback ako je matrica singularna
            
        # Ažurirano stanje
        self.x_ekf = x_pred + K @ Y
        
        # Ažurirana kovarijanca
        I = np.eye(8)
        self.P_ekf = (I - K @ H) @ P_pred
        
        self.ekf_last_time = current_time
        self.calc_pos = self.x_ekf[:3]
        
        # Izračunavanje GDOP-a (aproksimativno, koristeći H)
        try:
            # H_pos = H[:, [0,1,2,6]] (isto kao kod least squares)
            H_pos = H[:, [0,1,2,6]]
            Q_dop = np.linalg.inv(H_pos.T @ H_pos)
            gdop = np.sqrt(np.trace(Q_dop))
        except:
            gdop = None
            
        return self.calc_pos, gdop
