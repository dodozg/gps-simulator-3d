"""Mjerni model GNSS prijemnika: "svijet → pseudoudaljenosti".

Odvojeno od estimatora (EKF/RAIM u `receiver.py`, §19.2). Ovdje je SVE što
pretvara satelitske signale u mjerenja: vidljivost (elevacijska maska + LOS kroz
teren), signalni model (`signal_model.py`: link budget → C/N0, ometač i
cross-korelacija → efektivni C/N0 i gubitak zabrave, DLL pristranost i šum; ili
savršeno mjerenje u `ideal` modu), DOP selekcija praćenih satelita, iono-free kombinacija i sve korekcije
mjerenja (tropo, sat prijemnika/satelita, Sagnac, inter-system bias). Sat
prijemnika (Allanov šum) je dio mjerenja pa živi ovdje.

Model NE zna procjenu — estimator mu je predaje: `est_pos` (za DOP selekciju,
"prijemnik ne smije znati što ne bi znao") i `ref_pos` (približna pozicija za
troposfersku korekciju). Vraća listu mjerenja koju estimator riješi.
"""
import numpy as np

from physics_engine import (
    C, calculate_ionospheric_delay, calculate_tropospheric_delay,
    calculate_sagnac_correction, simulate_clock_noise, calculate_terrain_elevation,
    calculate_orbital_position,
)
from utils import ecef_to_lla, ecef_to_lla_array
import terrain
from satellite import GNSS_SYSTEMS
import signal_processing
import signal_model

MAX_SATS = 10           # gornja granica satelita u rješenju (vidi select_best_satellites)


class MeasurementModel:
    def __init__(self, pos=np.array([0.0, 0.0, 0.0]), rng=None, ideal=False):
        self.pos = pos
        # Generator slučajnih brojeva za sve izvore šuma (dijeli se s konstelacijom
        # radi reproducibilnosti). None -> svjež default_rng (nedeterministički).
        self.rng = rng if rng is not None else np.random.default_rng()
        # Zero-noise (ideal) mod: gasi multipath/AWGN/korelatorsku kvantizaciju
        # (savršeno mjerenje dometa), pogrešku efemerida i Allanov šum satova. Ostaju
        # SAMO deterministički modeli (geometrija, tropo, Sagnac, iono, ISB, relativnost).
        # Konstelacija se mora voziti istim modom: update_all(t, ideal=True).
        # Vidi tests/test_consistency.py.
        self.ideal = ideal

        # Sat prijemnika (dio MJERENJA — injektira se u pseudoudaljenost).
        self.clock_bias = 0.0    # [s]
        self.clock_drift = 1e-6  # [s/s] Početni drift za TCXO kvarc oscilator (1 ppm)
        self.h0 = 1e-19          # Allan variance parametri za kvarc
        self.h2 = 1e-20
        self.last_update_time = 0.0

        # Doba dana [s od ponoći UTC] za Klobuchar ionosferu (50400 = 14:00, dnevni
        # vrh TEC-a). Sim vrijeme se dodaje pa ionosfera evoluira kroz scenarij.
        self.iono_tow0 = 50400.0

        self.received_signals = []

        # Signalni model (signal_model.py): ometač i koherentna integracija.
        # jammer_jn_db postavlja napad (spoofing.Jamming) za TEKUĆU epohu.
        self.jammer_jn_db = 0.0
        self.t_coh_s = signal_model.T_COH_S
        self.n_visible = 0
        self.n_locked = 0
        self._vel_ref = None

    def set_position(self, pos):
        self.pos = pos

    @staticmethod
    def los_clear_many(sat_positions, rec_pos):
        """Vektorizirani check_los za više satelita: lista bool (True = put slobodan)."""
        sp = np.asarray(sat_positions, dtype=float)
        v = sp - rec_pos
        n = np.linalg.norm(v, axis=1, keepdims=True)
        n[n == 0] = 1.0
        d = np.arange(2000, 60000, 2000, dtype=float)
        pts = rec_pos + (v / n)[:, None, :] * d[None, :, None]      # (n_sat, n_uzoraka, 3)
        lat, lon, alt = ecef_to_lla_array(pts)
        h = terrain.elevation_array(lat.ravel(), lon.ravel()).reshape(lat.shape)
        return list(np.all(alt >= h, axis=1))

    def check_los(self, sat_pos, rec_pos):
        """Matematički raycasting: provjerava blokira li teren (planine) putanju signala."""
        vec = sat_pos - rec_pos
        dist = np.linalg.norm(vec)
        if dist == 0:
            return False
        direction = vec / dist
        # Uzorkujemo putanju do 60 km udaljenosti
        for d in np.arange(2000, 60000, 2000):
            test_p = rec_pos + direction * d
            lat, lon, alt = ecef_to_lla(test_p[0], test_p[1], test_p[2])
            terrain_h = calculate_terrain_elevation(lat, lon)
            if alt < terrain_h:
                return False  # Blokirano terenom!
        return True

    def build(self, constellation, current_time, est_pos=None, ref_pos=None):
        """Izgradi mjerenja (pseudoudaljenosti) za sve vidljive+odabrane satelite.

        est_pos: procijenjena pozicija (EKF) za DOP selekciju; None prije prvog fixa.
        ref_pos: približna pozicija za troposfersku korekciju (procjena ili a-priori).
        """
        self.received_signals = []

        dt = current_time - self.last_update_time
        if dt > 0:
            self.clock_bias, self.clock_drift = simulate_clock_noise(
                dt, self.clock_bias, self.clock_drift, self.h0, self.h2, rng=self.rng, ideal=self.ideal
            )
        self.last_update_time = current_time

        # Ako prijemnik još nije postavljen (u središtu Zemlje), ne može primati signale.
        if np.linalg.norm(self.pos) < 1.0:
            return self.received_signals

        if ref_pos is None:
            ref_pos = self.pos

        visible_signals = []
        for sat in constellation.satellites:
            sig = sat.get_signal(current_time)

            # 1. Čista geometrijska udaljenost (za potrebe simulacije kanala)
            vec = sig['pos'] - self.pos
            true_dist = np.linalg.norm(vec)
            if true_dist == 0:
                continue

            sat_dir = vec / true_dist
            rec_dir = self.pos / np.linalg.norm(self.pos)
            elevation = np.arcsin(np.dot(rec_dir, sat_dir))

            # Elevacijska maska: ignoriraj satelite ispod ~5°
            if elevation < np.radians(5):
                continue

            sig['true_dist'] = true_dist
            visible_signals.append((sat, sig))

        # LOS raycasting kroz teren (planine) — vektorizirano za sve kandidate
        # odjednom (jedan poziv DEM-a); iste točke uzorkovanja kao check_los.
        if visible_signals:
            clear = self.los_clear_many([sig['pos'] for _, sig in visible_signals], self.pos)
            visible_signals = [p for p, ok in zip(visible_signals, clear) if ok]

        iono_tow = self.iono_tow0 + current_time
        rx_vel = self._receiver_velocity(current_time)

        # --- Signalni model (signal_model.py): C/N0 svih vidljivih signala ------
        # Svi vidljivi signali dijele antenu: jedan ChannelBank po bandu računa
        # nominalni C/N0 (link budget), efektivni C/N0 uz ometač (J/N) i MAI
        # (cross-korelacija ostalih satelita nakon koherentne integracije uz
        # relativni Doppler). Satelit ispod praga zabrave na bilo kojem bandu se
        # NE prati (gubitak zabrave) — tek se među praćenima bira podskup (DOP).
        banks, cn0_eff = {}, {}
        if visible_signals:
            sat_pos = np.array([sig['pos'] for _, sig in visible_signals])
            sat_vel = np.array([self._sat_velocity(sat, current_time) for sat, _ in visible_signals])
            offs = np.array([float(getattr(sat, 'tx_power_offset_db', 0.0)) for sat, _ in visible_signals])
            ids = [sig['id'] for _, sig in visible_signals]
            ranges = [sig['true_dist'] for _, sig in visible_signals]
            for band in signal_model.BANDS:
                key = band.lower()
                freq = visible_signals[0][1][key]['freq']
                dop = signal_model.doppler_hz(sat_pos, sat_vel, self.pos, rx_vel, freq)
                cn0 = signal_model.cn0_dbhz(sat_pos, self.pos, band, offs)
                bank = signal_model.ChannelBank(ids, [sig[key]['prn'] for _, sig in visible_signals],
                                                ranges, dop, cn0, t_coh=self.t_coh_s,
                                                groups=[sat.system for sat, _ in visible_signals])
                banks[band] = bank
                if self.ideal:
                    # deterministički: bez MAI (ovisi o fazama), samo link budget + ometač
                    cn0_eff[band] = signal_model.effective_cn0_dbhz(cn0, self.jammer_jn_db)
                else:
                    cn0_eff[band] = bank.effective_cn0(self.jammer_jn_db)
            locked = np.ones(len(visible_signals), bool)
            for band in signal_model.BANDS:
                locked &= cn0_eff[band] >= signal_model.TRACK_THRESHOLD_DBHZ
            for idx, (sat, sig) in enumerate(visible_signals):
                sig['_bank_idx'] = idx
            tracked = [pair for pair, ok in zip(visible_signals, locked) if ok]
        else:
            tracked = []
        self.n_visible = len(visible_signals)
        self.n_locked = len(tracked)

        # Pametna selekcija najboljih satelita (DOP) iz PROCIJENJENE pozicije, ne prave.
        # Više satelita -> niži GDOP i bolja RAIM redundancija; empirijski optimum ~10
        # (preko toga su dodatni sateliti niske elevacije/bučniji).
        selected_pairs = self.select_best_satellites(tracked, max_sats=MAX_SATS, ref_pos=est_pos)

        for sat, sig in selected_pairs:
            idx = sig['_bank_idx']
            f1_2, f2_2 = sig['l1']['freq'] ** 2, sig['l2']['freq'] ** 2
            c_if1, c_if2 = f1_2 / (f1_2 - f2_2), f2_2 / (f1_2 - f2_2)   # iono-free koeficijenti
            cn1 = float(cn0_eff['L1'][idx])
            cn2 = float(cn0_eff['L2'][idx])
            # Šum koda iz C/N0 (DLL formula) — prijemnik ga zna iz vlastitih
            # parametara petlje i procjene C/N0 (kao prStdev u pravim prijemnicima).
            s1 = float(signal_model.dll_sigma_m(cn1, t_coh=self.t_coh_s))
            s2 = float(signal_model.dll_sigma_m(cn2, t_coh=self.t_coh_s))
            info = {
                'cn0_dbhz': cn1, 'cn0_l2_dbhz': cn2,
                'sigma_code_m': float(np.hypot(c_if1 * s1, c_if2 * s2)),
            }
            tropo = calculate_tropospheric_delay(sig['pos'], self.pos)
            iono_l1 = calculate_ionospheric_delay(sig['pos'], self.pos, sig['l1']['freq'], gps_tow_s=iono_tow)
            iono_l2 = calculate_ionospheric_delay(sig['pos'], self.pos, sig['l2']['freq'], gps_tow_s=iono_tow)
            true_dist = sig['true_dist']
            if self.ideal:
                # Zero-noise: savršeno mjerenje po satelitu (bez korelatora/šuma). Vidi
                # signal_processing.ideal_pseudorange i tests/test_consistency.py.
                m_l1 = signal_processing.ideal_pseudorange(true_dist, iono_l1 + tropo)
                m_l2 = signal_processing.ideal_pseudorange(true_dist, iono_l2 + tropo)
            else:
                elev_rad = float(np.arcsin(np.clip(np.dot(self.pos / np.linalg.norm(self.pos),
                                                          (sig['pos'] - self.pos) / true_dist), -1.0, 1.0)))
                mp_scale = float(np.clip(0.1 + 0.9 * (1.0 - max(np.sin(elev_rad), 0.05)), 0.1, 1.0))
                # Ista geometrija odraza za obje frekvencije -> KORELIRAN L1/L2 multipath.
                mp = signal_processing.sample_multipath(self.rng)
                b1, lost1 = banks['L1'].code_bias_m(idx, current_time, mp=mp, mp_scale=mp_scale)
                b2, lost2 = banks['L2'].code_bias_m(idx, current_time, mp=mp, mp_scale=mp_scale)
                n1, n2 = self.rng.normal(0.0, 1.0, 2)
                if lost1 or lost2:
                    continue      # DLL "uhvatio" cross-korelacijski vrh -> lock detektor ga odbaci
                m_l1 = true_dist + iono_l1 + tropo + b1 + s1 * n1
                m_l2 = true_dist + iono_l2 + tropo + b2 + s2 * n2
            entry = self._finalize(sat, sig, m_l1, m_l2, ref_pos)
            entry.update(info)
            self.received_signals.append(entry)

        return self.received_signals

    def _sat_velocity(self, sat, t, h=0.5):
        """ECEF brzina satelita (centralna razlika orbitalnog modela) — za Doppler."""
        if hasattr(sat, 'velocity_at'):          # prave orbite (SGP4) znaju svoju brzinu
            return np.asarray(sat.velocity_at(t), dtype=float)
        if not hasattr(sat, 'a'):
            return np.zeros(3)
        p1, _ = calculate_orbital_position(sat.a, sat.e, sat.i, sat.lan, sat.w, sat.m0, t + h)
        p0, _ = calculate_orbital_position(sat.a, sat.e, sat.i, sat.lan, sat.w, sat.m0, t - h)
        return (p1 - p0) / (2.0 * h)

    def _receiver_velocity(self, t):
        """Brzina prijemnika iz promjene prave pozicije između epoha (za Doppler)."""
        vel = np.zeros(3)
        if self._vel_ref is not None:
            p0, t0 = self._vel_ref
            if t > t0 and np.linalg.norm(self.pos - p0) < 1e5:
                vel = (self.pos - p0) / (t - t0)
        self._vel_ref = (np.array(self.pos, float), t)
        return vel

    def _finalize(self, sat, sig, measured_pr_l1, measured_pr_l2, ref_pos):
        """Iono-free kombinacija + sve korekcije mjerenja -> unos za received_signals.

        Zajedničko idealnom i per-sat putu. Redoslijed članova je bitan i dokumentiran:
        iono-free (poništi ionosferu) → −tropo (iz procjene) → + sat prijemnika →
        + stvarni sat satelita − broadcast korekcija (ponište se za ispravan satelit;
        spoof ostavlja rezidual za RAIM) → + Sagnac (mora biti i u mjerenju jer ga model
        korigira) → + ISB (EKF ga procjenjuje).
        """
        f1_2 = sig['l1']['freq'] ** 2
        f2_2 = sig['l2']['freq'] ** 2
        iono_free_pr = (f1_2 * measured_pr_l1 - f2_2 * measured_pr_l2) / (f1_2 - f2_2)

        iono_free_pr -= calculate_tropospheric_delay(sig['broadcast_pos'], ref_pos)
        iono_free_pr += (self.clock_bias * C)
        iono_free_pr += sig['sat_clock_m']
        iono_free_pr -= sig['broadcast_clock_m']
        iono_free_pr += calculate_sagnac_correction(sig['pos'], self.pos)
        iono_free_pr += GNSS_SYSTEMS.get(sat.system, {}).get('isb_m', 0.0)

        return {
            'sat_id': sig['id'],
            'system': sat.system,
            'sat_pos': sig['pos'],
            'broadcast_pos': sig['broadcast_pos'],   # Prijemnik ZNA samo ovu poziciju
            'pseudorange': iono_free_pr,
            'true_dist': sig['true_dist'],            # Spremljeno samo za analizu
        }

    def calculate_gdop(self, satellite_pairs, ref_pos):
        """GDOP podskupa satelita gledano iz ref_pos (procijenjene pozicije)."""
        H = []
        for sat, sig in satellite_pairs:
            vec = sig['broadcast_pos'] - ref_pos
            r = np.linalg.norm(vec)
            if r == 0:
                r = 1.0
            H.append([vec[0] / r, vec[1] / r, vec[2] / r, 1.0])
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
