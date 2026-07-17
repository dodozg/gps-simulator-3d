"""Navigacijski estimator: "pseudoudaljenosti → pozicija" (EKF + RAIM).

Odvojeno od mjernog modela (`measurement.MeasurementModel`, §19.2). `Receiver` JE
estimator (drži EKF stanje, RAIM, NIS dijagnostiku) i VLASI mjerni model kojemu
svaku epohu predaje trenutnu procjenu (za DOP selekciju i tropo korekciju), a
natrag dobiva mjerenja koja riješi. Javno sučelje `Receiver`-a je nepromijenjeno:
mjerno-strane atributi (pos, clock_bias, iono_tow0, ideal, received_signals…) se
proksiraju na mjerni model, estimatorski (x_ekf, raim_alarm, nis…) su izravni.
"""
import numpy as np
from physics_engine import calculate_sagnac_correction
from measurement import MeasurementModel

# --- Inter-system bias (ISB), multi-GNSS -------------------------------------
# Svaki GNSS sustav ima svoju vremensku skalu -> konstantni pomak pseudoudalje-
# nosti u odnosu na GPS. GPS je REFERENCA (ISB=0, upijen u c·bias); Galileo/
# GLONASS/BeiDou dobivaju vlastito ISB stanje u EKF-u koje se procjenjuje. Pravi
# ISB (GNSS_SYSTEMS[...]['isb_m']) se ubrizga u mjerenje (mjerni model), filter ga
# rekonstruira. (serialize.py uvozi ISB_INDEX odavde.)
ISB_SYSTEMS = ("GAL", "GLO", "BDS")
ISB_INDEX = {s: 8 + k for k, s in enumerate(ISB_SYSTEMS)}   # stanja 8,9,10
N_STATES = 8 + len(ISB_SYSTEMS)     # [x,y,z, vx,vy,vz, c·bias,c·drift, isb×3]
Q_ISB = 0.01                        # [m^2/s] procesni šum ISB-a (skoro konstantan)

# --- EKF parametri šuma (dokumentirano) ---------------------------------------
# Mjerni šum R: rezidualna pogreška pseudoudaljenosti (multipath + ephemeris +
# rezidual korekcija). Devijacija ovisi o elevaciji jer atmosfersko mapiranje
# (1/sin(elev)) i multipath rastu pri niskim elevacijama:
#     sigma(elev) = SIGMA_ZENITH / sin(elev)
# SIGMA_ZENITH daje NIS/dof ~ 1 (statistički konzistentan filter) NAKON popravaka
# ranging-a: 8× naduzorkovana korelacija (~2.5 m umjesto ~27 m), realan
# elevacijski-ovisan multipath (rezidual nakon mitigacije), troposferska
# korekcija, Sagnac član u mjerenju i realniji despread SNR (−2 dB umjesto −10).
# Prije je bilo 48 (dominirao grubi multipath 10–100 m + neriješeni Sagnac).
# Rezultat: greška pozicije ~4–6 m (mediana), vrhovi ~13 m; nepristrana (Sagnac
# fix). Vidi benchmark.py.
SIGMA_ZENITH = 1.9      # [m] devijacija pseudoudaljenosti u zenitu
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
    def __init__(self, pos=np.array([0.0, 0.0, 0.0]), rng=None, ideal=False):
        # Mjerni model: sve "svijet → pseudoudaljenosti" (kanal, korekcije, selekcija,
        # sat prijemnika). Estimator mu predaje procjenu, on vraća mjerenja.
        self.meas = MeasurementModel(pos, rng, ideal)

        self.raim_alarm = ""
        self.raim_enabled = True   # dopušta usporedbu algoritama sa/bez RAIM-a (#10)

        # EKF State: [x, y, z, vx, vy, vz, c*bias, c*drift, isb_GAL, isb_GLO, isb_BDS]
        self.ekf_initialized = False
        self.x_ekf = np.zeros(N_STATES)
        self.P_ekf = np.eye(N_STATES) * 1e6
        self.ekf_last_time = 0.0

        # Dijagnostika konzistentnosti filtera (NIS = Normalized Innovation Squared).
        # Za konzistentan filter NIS/dof ~ 1 (prati chi-kvadrat s dof = broj mjerenja).
        self.nis = 0.0
        self.nis_dof = 0
        self.last_solution = {}   # {sat_id: {residual_m, rejected}} — za web UI (#12)

    # --- Proxyji na mjerni model (nepromijenjeno javno sučelje) ---------------
    @property
    def pos(self):
        return self.meas.pos

    @pos.setter
    def pos(self, value):
        self.meas.pos = value

    @property
    def received_signals(self):
        return self.meas.received_signals

    @property
    def ideal(self):
        return self.meas.ideal

    @property
    def clock_bias(self):
        return self.meas.clock_bias

    @property
    def clock_drift(self):
        return self.meas.clock_drift

    @property
    def last_update_time(self):
        return self.meas.last_update_time

    @property
    def iono_tow0(self):
        return self.meas.iono_tow0

    @iono_tow0.setter
    def iono_tow0(self, value):
        self.meas.iono_tow0 = value

    def set_position(self, pos):
        self.meas.set_position(pos)

    def check_los(self, sat_pos, rec_pos):
        return self.meas.check_los(sat_pos, rec_pos)

    def select_best_satellites(self, visible_pairs, max_sats=6, ref_pos=None):
        return self.meas.select_best_satellites(visible_pairs, max_sats=max_sats, ref_pos=ref_pos)

    def receive_signals(self, constellation, current_time):
        """Izgradi mjerenja predajući mjernom modelu TRENUTNU procjenu.

        est_pos (za DOP selekciju) i ref_pos (za tropo korekciju) dolaze iz EKF-a;
        prije prvog fixa nema procjene pa selekcija uzima sve, a tropo se korigira
        iz a-priori (prave) pozicije.
        """
        est_pos = self.x_ekf[:3].copy() if self.ekf_initialized else None
        ref_pos = self.x_ekf[:3] if self.ekf_initialized else self.meas.pos
        return self.meas.build(constellation, current_time, est_pos=est_pos, ref_pos=ref_pos)

    def reset(self):
        self.ekf_initialized = False
        self.x_ekf = np.zeros(N_STATES)
        self.P_ekf = np.eye(N_STATES) * 1e6
        self.raim_alarm = ""
        self.ekf_last_time = 0.0
        self.last_solution = {}

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
        """Riješi poziciju iz mjerenja proširenim Kalmanovim filtrom (EKF) uz RAIM."""
        received_signals = self.received_signals
        if len(received_signals) < 4:
            return None, None

        self.raim_alarm = ""
        current_time = self.last_update_time

        # --- EKF INICIJALIZACIJA (Least Squares) ---
        if not self.ekf_initialized:
            x_ls = np.array([0.0, 0.0, 0.0, 0.0])
            for i in range(max_iter):
                residuals, jacobian = [], []
                for sig in received_signals:
                    sat_pos = sig['broadcast_pos']
                    pr = sig['pseudorange']
                    diff = x_ls[:3] - sat_pos
                    r_est = np.linalg.norm(diff)
                    if r_est < 1.0:
                        r_est = 1.0
                    sagnac = calculate_sagnac_correction(sat_pos, x_ls[:3])
                    res = pr - (r_est + x_ls[3] + sagnac)
                    residuals.append(res)
                    jacobian.append([diff[0] / r_est, diff[1] / r_est, diff[2] / r_est, 1.0])

                G = np.array(jacobian)
                try:
                    delta_x, _, _, _ = np.linalg.lstsq(G, np.array(residuals), rcond=None)
                except np.linalg.LinAlgError:
                    return None, None

                x_ls += delta_x
                if np.linalg.norm(delta_x[:3]) < tolerance:
                    self.x_ekf[0:3] = x_ls[:3]  # Pozicija
                    self.x_ekf[6] = x_ls[3]     # c*bias
                    self.ekf_initialized = True
                    self.ekf_last_time = current_time
                    break

            if not self.ekf_initialized:
                return None, None

        # --- EKF PREDVIĐANJE (PREDICT) ---
        dt = current_time - self.ekf_last_time
        if dt <= 0:
            dt = 1e-6  # Sprječavanje dijeljenja nulom

        F = np.eye(N_STATES)
        F[0, 3] = dt  # x += vx * dt
        F[1, 4] = dt  # y += vy * dt
        F[2, 5] = dt  # z += vz * dt
        F[6, 7] = dt  # c*bias += c*drift * dt
        # ISB stanja (8..10) su konstantna (F dijagonala već 1).

        # Procesni šum Q (nesigurnost modela) — parametri dokumentirani na vrhu modula.
        Q = np.diag([Q_POS, Q_POS, Q_POS, Q_VEL, Q_VEL, Q_VEL, Q_BIAS, Q_DRIFT]
                    + [Q_ISB] * len(ISB_SYSTEMS)) * dt

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
        for sig in received_signals:
            sat_pos = sig['broadcast_pos']
            pr = sig['pseudorange']

            diff = x_pred[:3] - sat_pos
            r_est = np.linalg.norm(diff)
            if r_est < 1.0:
                r_est = 1.0

            sagnac = calculate_sagnac_correction(sat_pos, x_pred[:3])
            # Predviđeni ISB ovog sustava (GPS -> 0, upijen u c·bias).
            isb_idx = ISB_INDEX.get(sig.get('system'))
            isb = x_pred[isb_idx] if isb_idx is not None else 0.0
            h_x_val = r_est + x_pred[6] + sagnac + isb
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
            ids = ", ".join(received_signals[i]['sat_id'] for i in sorted(rejected))
            self.raim_alarm = f"RAIM ALARM: Rejected {ids} (Err: {worst:.0f}m)"

        # Dijagnostika po satelitu za vanjske potrošače (web UI): rezidual inovacije
        # i je li ga RAIM odbacio. Samo se sprema — ne utječe na rješenje.
        self.last_solution = {
            sig['sat_id']: {'residual_m': float(all_innovations[i][0]),
                            'rejected': i in rejected}
            for i, sig in enumerate(received_signals)
        }

        for i, sig in enumerate(received_signals):
            if i in rejected:
                continue
            innovation, h_x_val, diff, r_est = all_innovations[i]

            H_row = np.zeros(N_STATES)
            H_row[0] = diff[0] / r_est
            H_row[1] = diff[1] / r_est
            H_row[2] = diff[2] / r_est
            H_row[6] = 1.0  # c*bias
            isb_idx = ISB_INDEX.get(sig.get('system'))
            if isb_idx is not None:
                H_row[isb_idx] = 1.0   # ovaj sustav ima vlastiti ISB

            H_valid.append(H_row)
            Z_valid.append(sig['pseudorange'])
            h_x_valid.append(h_x_val)

            # Adaptivni mjerni šum: sigma raste s 1/sin(elev). diff = est - sat,
            # pa je smjer prema satelitu -diff; sin(elev) = up · (sat - est)/r.
            sin_elev = np.dot(up, -diff / r_est)
            sin_elev = max(sin_elev, MIN_SIN_ELEV)
            R_diag.append((SIGMA_ZENITH / sin_elev) ** 2)

        if len(H_valid) < 4:
            return None, None  # RAIM odbacio previše satelita

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
            return x_pred[:3], None  # Fallback ako je matrica singularna
        K = P_pred @ H.T @ S_inv

        # NIS (Normalized Innovation Squared) — dijagnostika konzistentnosti.
        # Za dobro podešen filter NIS/dof ~ 1. Trajno >1 znači preoptimističan R
        # (filter podcjenjuje šum); <1 znači prekonzervativan.
        self.nis = float(Y @ S_inv @ Y)
        self.nis_dof = len(H_valid)

        # Ažurirano stanje
        self.x_ekf = x_pred + K @ Y

        # Ažurirana kovarijanca
        I = np.eye(N_STATES)
        self.P_ekf = (I - K @ H) @ P_pred

        self.ekf_last_time = current_time
        self.calc_pos = self.x_ekf[:3]

        # Izračunavanje GDOP-a (aproksimativno, koristeći H)
        try:
            # H_pos = H[:, [0,1,2,6]] (isto kao kod least squares)
            H_pos = H[:, [0, 1, 2, 6]]
            Q_dop = np.linalg.inv(H_pos.T @ H_pos)
            gdop = np.sqrt(np.trace(Q_dop))
        except Exception:
            gdop = None

        return self.calc_pos, gdop
