import numpy as np
from physics_engine import C, calculate_ionospheric_delay, calculate_tropospheric_delay, calculate_sagnac_correction, simulate_clock_noise, calculate_terrain_elevation, R_EARTH
from utils import ecef_to_lla
import signal_processing

# --- EKF parametri šuma (dokumentirano) ---------------------------------------
# Mjerni šum R: pseudoudaljenost u ovom simulatoru nosi rezidualni multipath,
# troposferu i ephemeris pogrešku. Modeliramo standardnu devijaciju kao funkciju
# elevacije jer atmosfersko mapiranje (1/sin(elev)) pojačava pogrešku pri niskim
# elevacijama:   sigma(elev) = SIGMA_ZENITH / sin(elev)
# SIGMA_ZENITH=48 je podešen tako da NIS/dof ~ 1 (filter je statistički
# konzistentan): stvarni šum je dominiran pristranim multipath-om pa je ~4x
# veći od naivne procjene od ~12 m. Vrijednost je recentrirana s 40 na 48 nakon
# što determinističko biranje po GDOP-u uključuje i niže-elevacijske satelite
# (bolja geometrija, ali veći šum). Vidi benchmark.py za mjerenje.
SIGMA_ZENITH = 48.0     # [m] devijacija pseudoudaljenosti u zenitu
MIN_SIN_ELEV = 0.1      # granica (~5.7°) da R ne eksplodira na horizontu

# Procesni šum Q (nesigurnost modela gibanja/sata) po jedinici vremena [/s].
# Veći iznos = filter više vjeruje mjerenjima nego predviđanju.
Q_POS = 0.5             # [m^2/s]   šum položaja
Q_VEL = 1.0             # [ (m/s)^2/s ] šum brzine
Q_BIAS = 5.0            # [m^2/s]   šum pomaka sata (c*bias)
Q_DRIFT = 1.0           # [ (m/s)^2/s ] šum drifta sata (c*drift)

# --- RAIM parametri (iterativna, robusna detekcija outliera) ------------------
# Odbacujemo satelit čija inovacija odstupa od medijane više od RAIM_K robusnih
# sigma (MAD skala) I više od apsolutnog praga RAIM_MIN_ABS. Postupak je
# iterativan (najveći outlier prvo) pa hvata i više istovremeno pokvarenih
# satelita, a MAD skala se prilagođava razini šuma umjesto fiksnog praga.
RAIM_K = 6.0            # broj robusnih sigma za odbacivanje
RAIM_MIN_ABS = 600.0    # [m] apsolutni prag (ispod = normalni multipath, ne diramo)
RAIM_MIN_SATS = 5       # ne odbacuj ako bi ostalo < 4 satelita za rješenje


class Receiver:
    def __init__(self, pos=np.array([0.0, 0.0, 0.0]), rng=None):
        self.pos = pos
        # Generator slučajnih brojeva za sve izvore šuma (dijeli se s konstelacijom
        # radi reproducibilnosti). None -> svjež default_rng (nedeterministički).
        self.rng = rng if rng is not None else np.random.default_rng()
        self.clock_bias = 0.0 # [s]
        self.clock_drift = 1e-6 # [s/s] Početni drift za TCXO kvarc oscilator (1 ppm)
        self.h0 = 1e-19 # Allan variance parametri za kvarc
        self.h2 = 1e-20
        self.last_update_time = 0.0
        self.raim_alarm = ""
        self.raim_enabled = True   # dopušta usporedbu algoritama sa/bez RAIM-a (#10)
        # Doba dana [s od ponoći UTC] za Klobuchar ionosferu (50400 = 14:00, dnevni
        # vrh TEC-a). Sim vrijeme se dodaje pa ionosfera evoluira kroz scenarij.
        self.iono_tow0 = 50400.0

        # EKF State
        self.ekf_initialized = False
        self.x_ekf = np.zeros(8) # [x, y, z, vx, vy, vz, c*bias, c*drift]
        self.P_ekf = np.eye(8) * 1e6
        self.ekf_last_time = 0.0

        # Dijagnostika konzistentnosti filtera (NIS = Normalized Innovation Squared).
        # Za konzistentan filter NIS/dof ~ 1 (prati chi-kvadrat s dof = broj mjerenja).
        self.nis = 0.0
        self.nis_dof = 0

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
                dt, self.clock_bias, self.clock_drift, self.h0, self.h2, rng=self.rng
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
            
        # Pametna selekcija najboljih satelita (DOP Optimization) iz PROCIJENJENE
        # pozicije (EKF), ne iz prave. Prije prvog fixa nemamo procjenu -> None.
        est_pos = self.x_ekf[:3].copy() if self.ekf_initialized else None
        selected_pairs = self.select_best_satellites(visible_signals, max_sats=6, ref_pos=est_pos)
        
        for sat, sig in selected_pairs:
            true_dist = sig['true_dist']
            
            # 3. Atmosfersko kašnjenje
            tropo_delay_meters = calculate_tropospheric_delay(sig['pos'], self.pos)
            
            # L1 Obrada — Klobuchar ionosfera ovisna o dobu dana (#7)
            iono_tow = self.iono_tow0 + current_time
            iono_delay_l1 = calculate_ionospheric_delay(sig['pos'], self.pos, sig['l1']['freq'], gps_tow_s=iono_tow)
            rx_signal_l1, int_blocks_l1 = signal_processing.simulate_rf_channel(
                prn=sig['l1']['prn'], distance=true_dist, iono_delay_meters=iono_delay_l1+tropo_delay_meters, snr_db=-10, rng=self.rng
            )
            local_prn_l1 = signal_processing.generate_prn(sat.sat_id + "_L1")
            measured_pr_l1 = signal_processing.decode_signal(rx_signal_l1, local_prn_l1, int_blocks_l1)
            
            # L2 Obrada (isto doba dana; iono-free kombinacija ga poništava)
            iono_delay_l2 = calculate_ionospheric_delay(sig['pos'], self.pos, sig['l2']['freq'], gps_tow_s=iono_tow)
            rx_signal_l2, int_blocks_l2 = signal_processing.simulate_rf_channel(
                prn=sig['l2']['prn'], distance=true_dist, iono_delay_meters=iono_delay_l2+tropo_delay_meters, snr_db=-10, rng=self.rng
            )
            local_prn_l2 = signal_processing.generate_prn(sat.sat_id + "_L2")
            measured_pr_l2 = signal_processing.decode_signal(rx_signal_l2, local_prn_l2, int_blocks_l2)
            
            # Iono-Free kombinacija
            f1_2 = sig['l1']['freq']**2
            f2_2 = sig['l2']['freq']**2
            iono_free_pr = (f1_2 * measured_pr_l1 - f2_2 * measured_pr_l2) / (f1_2 - f2_2)
            
            # Dodajemo pogrešku sata prijemnika (bias) na kombinaciju
            iono_free_pr += (self.clock_bias * C)

            # Ubrizgavamo STVARNU grešku satelitskog sata (relativnost + Allan + eventualni spoof),
            # a zatim oduzimamo BROADCAST korekciju iz navigacijske poruke.
            # Za ispravan satelit se ova dva člana ponište (kao u stvarnom GPS-u);
            # za spoofani satelit ostaje rezidual od 6 km koji RAIM mora uhvatiti.
            iono_free_pr += sig['sat_clock_m']
            iono_free_pr -= sig['broadcast_clock_m']
            
            self.received_signals.append({
                'sat_id': sig['id'],
                'sat_pos': sig['pos'],
                'broadcast_pos': sig['broadcast_pos'], # Prijemnik ZNA samo ovu poziciju
                'pseudorange': iono_free_pr,
                'true_dist': true_dist # Spremljeno samo za analizu
            })
            
        return self.received_signals

    def calculate_gdop(self, satellite_pairs, ref_pos):
        """GDOP podskupa satelita gledano iz ref_pos (procijenjene pozicije)."""
        H = []
        for sat, sig in satellite_pairs:
            vec = sig['broadcast_pos'] - ref_pos
            r = np.linalg.norm(vec)
            if r == 0: r = 1.0
            H.append([vec[0]/r, vec[1]/r, vec[2]/r, 1.0])
        H = np.array(H)
        try:
            cov = np.linalg.inv(H.T @ H)
            return np.sqrt(np.trace(cov))
        except np.linalg.LinAlgError:
            return float('inf')

    def _elevation(self, pair, ref_pos):
        """Elevacijski kut satelita gledano iz ref_pos."""
        _, sig = pair
        vec = sig['broadcast_pos'] - ref_pos
        n = np.linalg.norm(vec)
        rp = np.linalg.norm(ref_pos)
        if n == 0 or rp == 0:
            return 0.0
        up = ref_pos / rp
        return np.arcsin(np.clip(np.dot(up, vec / n), -1.0, 1.0))

    def select_best_satellites(self, visible_pairs, max_sats=6, ref_pos=None):
        """Bira podskup satelita s najboljom geometrijom (najniži GDOP).

        Determinističko pohlepno biranje umjesto ranijeg nasumičnog Monte-Carla,
        i to iz PROCIJENJENE pozicije (ref_pos) — ne iz prave pozicije koju pravi
        prijemnik ne zna. Prije prvog fixa (ref_pos=None) nema procjene geometrije
        pa uzimamo sve vidljive (do granice) za robusnu LS inicijalizaciju.
        """
        if len(visible_pairs) <= max_sats:
            return visible_pairs

        if ref_pos is None:
            # Hladan start: bez procjene ne možemo optimizirati geometriju.
            return visible_pairs[:max(max_sats, 8)]

        # Pohlepno: seedaj s najviše elevacije (dok ih je < 4 GDOP nije definiran),
        # zatim dodaji satelit koji najviše smanji GDOP.
        remaining = list(visible_pairs)
        chosen = []
        while len(chosen) < max_sats and remaining:
            best, best_score = None, float('inf')
            for cand in remaining:
                trial = chosen + [cand]
                if len(trial) < 4:
                    score = -self._elevation(cand, ref_pos)  # veća elevacija = bolji seed
                else:
                    score = self.calculate_gdop(trial, ref_pos)
                if score < best_score:
                    best_score, best = score, cand
            chosen.append(best)
            remaining.remove(best)
        return chosen

    def _raim_screen(self, innovations):
        """Iterativna robusna RAIM detekcija: vrati skup indeksa za odbacivanje.

        U svakom koraku nađe satelit čija inovacija najviše odstupa od medijane;
        ako prelazi RAIM_K robusnih sigma (MAD skala) I apsolutni prag
        RAIM_MIN_ABS, odbaci ga i ponovi. Tako hvata i više istovremeno pokvarenih
        satelita, a MAD skala se prilagođava razini šuma (bez fiksnog praga).
        """
        inn = np.asarray(innovations, dtype=float)
        active = list(range(len(inn)))
        rejected = set()
        while len(active) >= RAIM_MIN_SATS:
            vals = inn[active]
            med = np.median(vals)
            mad = 1.4826 * np.median(np.abs(vals - med))
            scale = max(mad, SIGMA_ZENITH)
            resid = np.abs(vals - med)
            k = int(np.argmax(resid))
            if resid[k] > RAIM_K * scale and resid[k] > RAIM_MIN_ABS:
                rejected.add(active[k])
                active.pop(k)
            else:
                break
        return rejected

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
        
        # Procesni šum Q (nesigurnost modela) — parametri dokumentirani na vrhu modula.
        Q = np.diag([Q_POS, Q_POS, Q_POS, Q_VEL, Q_VEL, Q_VEL, Q_BIAS, Q_DRIFT]) * dt
        
        # Predviđanje stanja i kovarijance
        x_pred = F @ self.x_ekf
        P_pred = F @ self.P_ekf @ F.T + Q
        
        # --- EKF AŽURIRANJE (UPDATE) ---
        # Validni signali za H i Z (filtrirani RAIM-om)
        H_valid = []
        Z_valid = []
        h_x_valid = []
        R_diag = []  # dijagonala mjernog šuma, po satelitu (ovisi o elevaciji)

        # Lokalni zenit za računanje elevacije (iz trenutne procjene položaja)
        up = x_pred[:3] / max(np.linalg.norm(x_pred[:3]), 1.0)
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
            
        # RAIM: iterativno robusno odbacivanje outliera (vidi _raim_screen).
        innov_list = [x[0] for x in all_innovations]
        rejected = (self._raim_screen(innov_list)
                    if (self.ekf_initialized and self.raim_enabled) else set())
        if rejected:
            kept = [innov_list[i] for i in range(len(innov_list)) if i not in rejected]
            med_kept = np.median(kept) if kept else 0.0
            worst = max(abs(innov_list[i] - med_kept) for i in rejected)
            ids = ", ".join(self.received_signals[i]['sat_id'] for i in sorted(rejected))
            self.raim_alarm = f"RAIM ALARM: Rejected {ids} (Err: {worst:.0f}m)"

        for i, sig in enumerate(self.received_signals):
            if i in rejected:
                continue
            innovation, h_x_val, diff, r_est = all_innovations[i]

            H_row = np.zeros(8)
            H_row[0] = diff[0] / r_est
            H_row[1] = diff[1] / r_est
            H_row[2] = diff[2] / r_est
            H_row[6] = 1.0 # c*bias

            H_valid.append(H_row)
            Z_valid.append(sig['pseudorange'])
            h_x_valid.append(h_x_val)

            # Adaptivni mjerni šum: sigma raste s 1/sin(elev). diff = est - sat,
            # pa je smjer prema satelitu -diff; sin(elev) = up · (sat - est)/r.
            sin_elev = np.dot(up, -diff / r_est)
            sin_elev = max(sin_elev, MIN_SIN_ELEV)
            R_diag.append((SIGMA_ZENITH / sin_elev) ** 2)

        if len(H_valid) < 4:
            return None, None # RAIM odbacio previše satelita

        H = np.array(H_valid)
        Z = np.array(Z_valid)
        h_x = np.array(h_x_valid)

        # Mjerni šum R: dijagonala s elevacijski ovisnim varijancama (vidi vrh modula).
        R = np.diag(R_diag)

        # Inovacijska kovarijanca S
        S = H @ P_pred @ H.T + R

        # Inovacija (razlika između mjerenog i predviđenog)
        Y = Z - h_x
        
        # Kalman gain K
        try:
            S_inv = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return x_pred[:3], None # Fallback ako je matrica singularna
        K = P_pred @ H.T @ S_inv

        # NIS (Normalized Innovation Squared) — dijagnostika konzistentnosti.
        # Za dobro podešen filter NIS/dof ~ 1. Trajno >1 znači preoptimističan R
        # (filter podcjenjuje šum); <1 znači prekonzervativan.
        self.nis = float(Y @ S_inv @ Y)
        self.nis_dof = len(H_valid)

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
