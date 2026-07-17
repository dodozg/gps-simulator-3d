"""Mjerni model GNSS prijemnika: "svijet → pseudoudaljenosti".

Odvojeno od estimatora (EKF/RAIM u `receiver.py`, §19.2). Ovdje je SVE što
pretvara satelitske signale u mjerenja: vidljivost (elevacijska maska + LOS kroz
teren), DOP selekcija satelita, RF kanal (Gold kodovi + multipath + AWGN, ili
savršeno mjerenje u `ideal` modu), iono-free kombinacija i sve korekcije
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
)
from utils import ecef_to_lla
from satellite import GNSS_SYSTEMS
import signal_processing

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

    def set_position(self, pos):
        self.pos = pos

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
            # LOS raycasting provjerava planine
            if not self.check_los(sig['pos'], self.pos):
                continue

            sig['true_dist'] = true_dist
            visible_signals.append((sat, sig))

        # Pametna selekcija najboljih satelita (DOP) iz PROCIJENJENE pozicije, ne prave.
        # Više satelita -> niži GDOP i bolja RAIM redundancija; empirijski optimum ~10
        # (preko toga su dodatni sateliti niske elevacije/bučniji).
        selected_pairs = self.select_best_satellites(visible_signals, max_sats=MAX_SATS, ref_pos=est_pos)
        iono_tow = self.iono_tow0 + current_time

        if self.ideal:
            # Zero-noise: savršeno mjerenje po satelitu (bez RF lanca). Vidi
            # signal_processing.ideal_pseudorange i tests/test_consistency.py.
            for sat, sig in selected_pairs:
                iono_l1 = calculate_ionospheric_delay(sig['pos'], self.pos, sig['l1']['freq'], gps_tow_s=iono_tow)
                iono_l2 = calculate_ionospheric_delay(sig['pos'], self.pos, sig['l2']['freq'], gps_tow_s=iono_tow)
                tropo = calculate_tropospheric_delay(sig['pos'], self.pos)
                m_l1 = signal_processing.ideal_pseudorange(sig['true_dist'], iono_l1 + tropo)
                m_l2 = signal_processing.ideal_pseudorange(sig['true_dist'], iono_l2 + tropo)
                self.received_signals.append(self._finalize(sat, sig, m_l1, m_l2, ref_pos))
            return self.received_signals

        # --- Per-satelitski kanal (zadano) ---------------------------------------
        # Svaki satelit se dekodira iz vlastitog kanala (bez zbrajanja u zajednički
        # antenski signal). To NIJE pojednostavljenje na štetu realizma: pravi
        # prijemnik integrira korelaciju kroz mnogo kodnih perioda (uz relativni
        # Doppler), pa se cross-korelacija između satelita usredni prema NULI — a
        # per-sat kanal upravo modelira taj (dobro razdvojeni) ishod. Jedan snapshot
        # kombiniranog signala precjenjuje cross-korelaciju (mjereno ~5→10 m, NIS↑),
        # jer izostavlja tu vremensku integraciju. Puni model (Doppler + koherentna
        # integracija → stvaran near-far/jamming) je u planu (vidi §10 dokumentacije).
        for sat, sig in selected_pairs:
            true_dist = sig['true_dist']
            svec = sig['pos'] - self.pos
            sn = np.linalg.norm(svec)
            rn = np.linalg.norm(self.pos)
            elev_rad = float(np.arcsin(np.clip(np.dot(self.pos / rn, svec / sn), -1.0, 1.0))) if sn > 0 and rn > 0 else None
            tropo = calculate_tropospheric_delay(sig['pos'], self.pos)
            iono_l1 = calculate_ionospheric_delay(sig['pos'], self.pos, sig['l1']['freq'], gps_tow_s=iono_tow)
            iono_l2 = calculate_ionospheric_delay(sig['pos'], self.pos, sig['l2']['freq'], gps_tow_s=iono_tow)
            # Ista geometrija odraza za obje frekvencije -> KORELIRAN L1/L2 multipath.
            mp = signal_processing.sample_multipath(self.rng)
            m_l1 = signal_processing.simulate_channel(sig['l1']['prn'], true_dist + iono_l1 + tropo, snr_db=-2, rng=self.rng, elev_rad=elev_rad, mp=mp)
            m_l2 = signal_processing.simulate_channel(sig['l2']['prn'], true_dist + iono_l2 + tropo, snr_db=-2, rng=self.rng, elev_rad=elev_rad, mp=mp)
            self.received_signals.append(self._finalize(sat, sig, m_l1, m_l2, ref_pos))

        return self.received_signals

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
