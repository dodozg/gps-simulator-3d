"""Signalni model (signal_model.py): link budget → C/N0, DLL šum, potiskivanje
cross-korelacije koherentnom integracijom + Dopplerom, near-far, jamming u signalu."""
import time

import numpy as np

import signal_model as sm
import signal_processing as sp
from measurement import MeasurementModel
from satellite import WalkerDeltaConstellation, MultiGNSSConstellation
from utils import lla_to_ecef

ZAGREB = (45.815, 15.982, 120.0)


def _sat_at(rx, el_deg, alt=20200e3, az_east=True):
    """ECEF pozicija satelita na zadanoj elevaciji (azimut istok) iznad rx."""
    up = rx / np.linalg.norm(rx)
    east = np.cross([0.0, 0.0, 1.0], up)
    east /= np.linalg.norm(east)
    e = np.radians(el_deg)
    R = np.linalg.norm(rx)
    r = 6371e3 + alt
    d = -R * np.sin(e) + np.sqrt((R * np.sin(e)) ** 2 + r ** 2 - R ** 2)
    return rx + d * (np.sin(e) * up + np.cos(e) * east)


def test_cn0_vs_elevation_is_realistic():
    rx = np.array(lla_to_ecef(*ZAGREB))
    els = [5, 10, 20, 30, 45, 60, 90]
    c1 = np.array([sm.cn0_dbhz(_sat_at(rx, e), rx, "L1")[0] for e in els])
    c2 = np.array([sm.cn0_dbhz(_sat_at(rx, e), rx, "L2")[0] for e in els])
    assert np.all(np.diff(c1) > 0)                       # raste s elevacijom (antena)
    assert 47.0 < c1[-1] < 51.0                          # zenit ~49 dB-Hz
    assert 36.0 < c1[0] < 41.0                           # 5° ~39 dB-Hz
    np.testing.assert_allclose(c1 - c2, 3.0, atol=1e-9)  # L2 ~3 dB slabiji
    # udaljeniji sustav (Galileo, 23 222 km) je slabiji, bliži (GLONASS) jači
    gal = sm.cn0_dbhz(_sat_at(rx, 45, alt=23222e3), rx)[0]
    glo = sm.cn0_dbhz(_sat_at(rx, 45, alt=19100e3), rx)[0]
    assert glo > c1[4] > gal
    # ispod horizonta nema signala
    below = rx - 2e7 * rx / np.linalg.norm(rx)
    assert sm.cn0_dbhz(below, rx)[0] == -np.inf


def test_dll_noise_follows_theory():
    # σ² = B_L·d/(2·C/N0)·(1 + 2/((2−d)·T·C/N0)) — referentna vrijednost (Kaplan):
    # 45 dB-Hz, B_L = 1 Hz, d = 1 čip, T = 20 ms → σ ≈ 0,00398 čipa ≈ 1,17 m.
    s = sm.dll_sigma_chips(45.0, t_coh=0.02, bl_hz=1.0, d=1.0)
    assert abs(s - 0.003982) < 2e-6
    # Visoki C/N0: σ ∝ 1/√(C/N0) (10 dB → √10×), ∝ √B_L, ∝ √d.
    r = sm.dll_sigma_chips(40.0) / sm.dll_sigma_chips(50.0)
    assert abs(r - np.sqrt(10.0)) / np.sqrt(10.0) < 0.02
    assert abs(sm.dll_sigma_chips(45, bl_hz=4.0) / sm.dll_sigma_chips(45, bl_hz=1.0) - 2.0) < 1e-9
    assert sm.dll_sigma_chips(45, d=0.25) < sm.dll_sigma_chips(45, d=0.5)
    # Nizak C/N0: gubitak kvadriranja raste, kraća integracija je bučnija.
    lo = 22.0
    assert sm.dll_sigma_chips(lo, t_coh=0.001) > 1.3 * sm.dll_sigma_chips(lo, t_coh=0.02)


def test_chain_ranging_noise_matches_reported_cn0_sigma():
    """Raspršenje pseudoudaljenosti u STVARNOM lancu (MeasurementModel) prati
    `sigma_code_m` iz C/N0 — i pod ometačem (J/N = 12 dB) raste kako teorija kaže."""
    rng = np.random.default_rng(5)
    con = WalkerDeltaConstellation(rng=rng)
    con.update_all(100.0)
    rx = np.array(lla_to_ecef(*ZAGREB))
    for jn in (0.0, 12.0):
        mm = MeasurementModel(rx, rng=np.random.default_rng(11))
        mm.jammer_jn_db = jn
        mm.build(con, 100.0)                             # prva epoha postavi sat (dt>0)
        prs, sig = {}, {}
        for _ in range(400):
            for m in mm.build(con, 100.0):               # isti trenutak → ista geometrija
                prs.setdefault(m['sat_id'], []).append(m['pseudorange'])
                sig[m['sat_id']] = m['sigma_code_m']
        ratios = [np.std(prs[k]) / sig[k] for k in prs]
        # multipath (dijeljen L1/L2, ~0,1–0,5 m) malo napuhuje raspršenje
        assert 0.9 < np.median(ratios) < 1.2, (jn, ratios)
        if jn == 0.0:
            base = np.median(list(sig.values()))
        else:
            # σ ∝ 1/√(C/N0_eff): 12 dB ometača → 10^(10·log10(1+15.85)/20) ≈ 4.1×
            assert 3.5 < np.median(list(sig.values())) / base < 4.6


def test_crosscorrelation_suppressed_by_coherent_integration_and_doppler():
    a, b = sp.gold_code(0), sp.gold_code(100)
    # Doppler bin 0: pravi Gold kod — troznačno {−65, −1, 63}/1023
    x0 = np.rint(sm.xcorr(a, b, np.arange(1023.0)).real * 1023)
    assert set(np.unique(x0)).issubset({-65, -1, 63})
    # Doppler-pomaknuti bin je i dalje omeđen (~ −21 dB najgore), ne kao auto-vrh
    xm = np.abs(sm.xcorr(a, b, np.arange(1023.0), m=3))
    assert xm.max() < 0.12
    # Koherentna integracija T: interferencija na rel. Doppleru δ prigušena sinc(πδT)
    assert sm.coherent_gain(0.0) == 1.0
    for df in (137.0, 263.0, 412.0):
        g1, g20 = sm.coherent_gain(df, 0.001), sm.coherent_gain(df, 0.020)
        assert g1 > 0.7 and g20 < 0.12 * g1
    # Snaga cross-korelacije koja prođe integraciju: usrednjeno po Doppleru daje
    # poznati C/A spektralni koeficijent razdvajanja ≈ −61,8 dB/Hz ...
    ssc = 10 * np.log10(np.mean(sm.mai_kappa(np.linspace(0.0, 1000.0, 20001))))
    assert abs(ssc - (-61.8)) < 0.3
    # ... a za konkretan par dulja integracija jako potiskuje (N0/C ekvivalent).
    assert sm.mai_kappa(137.0, 0.020) < 0.2 * sm.mai_kappa(137.0, 0.001)
    assert sm.mai_kappa(263.0, 0.020) < 0.07 * sm.mai_kappa(263.0, 0.001)
    # Snapshot od 1 ms (stari kombinirani model) NE potiskuje: κ(T=1ms) ≈ T·⟨X²⟩·(…)
    assert sm.mai_kappa(137.0, 0.001) > 0.5 * 0.001 * sm.X_MS


def test_code_bias_from_crosscorrelation_depends_on_doppler_match():
    """Koherentna pristranost DLL-a od jednako jakog satelita: velika kad je
    relativni Doppler ~višekratnik 1 kHz (petlja je ne može usrednjiti), ~0 inače."""
    codes = [sp.gold_code(0), sp.gold_code(100)]
    ranges = [21_000_000.0, 21_000_000.0 + 0.3 * sp.PRN_LENGTH * sp.METERS_PER_CHIP]

    def worst_bias(df):
        bank = sm.ChannelBank(["A", "B"], codes, ranges, [0.0, df], [45.0, 45.0])
        return max(abs(bank.code_bias_m(0, t)[0]) for t in np.linspace(0, 10, 41))

    near = worst_bias(2000.0 + 0.05)          # 2 kHz + 0,05 Hz otkucaj
    far = worst_bias(2000.0 + 180.0)          # 180 Hz od linije
    assert near > 0.2                          # metarska pristranost
    assert far < 0.01 * near + 1e-9           # potisnuto sinc·petlja


def _cn0_by_id(mm, con, t):
    return {m['sat_id']: m for m in mm.build(con, t)}


def test_near_far_bank_level():
    """Jak signal (+25 dB) blizu spektralne linije slabog (δ = 10 Hz) mu sruši
    C/N0 za desetke dB i odnese zabravu; daleko od linije (δ = 400 Hz) ~ništa."""
    codes = [sp.gold_code(7), sp.gold_code(300)]
    ranges = [21.0e6, 22.3e6]

    def weak_cn0(df, boost):
        bank = sm.ChannelBank(["W", "S"], codes, ranges, [0.0, df], [42.0, 42.0 + boost])
        return float(bank.effective_cn0(0.0)[0])

    assert 42.0 - weak_cn0(3010.0, 0.0) < 1.0               # jednako jak: malo (< 1 dB)
    assert 42.0 - weak_cn0(3400.0, 25.0) < 1.0              # jak, ali daleko od linije
    assert weak_cn0(3010.0, 25.0) < sm.TRACK_THRESHOLD_DBHZ  # jak + blizu linije: gubi zabravu


def test_near_far_strong_satellite_degrades_weak_ones():
    """U lancu: satelit pojačan za +25 dB (npr. spoofer) kroz vrijeme (Doppleri
    klize) degradira ostale — dio epoha za > 3 dB, ponekad i do gubitka zabrave."""
    rng = np.random.default_rng(3)
    con = WalkerDeltaConstellation(rng=rng)              # MAI djeluje unutar sustava
    for s in con.satellites:
        s.is_spoofed = False
    rx = np.array(lla_to_ecef(*ZAGREB))
    drops, grow, lost = [], [], 0
    for t in np.arange(50.0, 450.0, 20.0):
        con.update_all(t)
        base = _cn0_by_id(MeasurementModel(rx, rng=np.random.default_rng(1)), con, t)
        strong_id = sorted(base)[0]
        strong = next(s for s in con.satellites if s.sat_id == strong_id)
        strong.tx_power_offset_db = 25.0
        nf = _cn0_by_id(MeasurementModel(rx, rng=np.random.default_rng(1)), con, t)
        strong.tx_power_offset_db = 0.0
        assert nf[strong_id]['cn0_dbhz'] > base[strong_id]['cn0_dbhz'] + 24.0
        for k in base:
            if k == strong_id:
                continue
            if k in nf:
                drops.append(base[k]['cn0_dbhz'] - nf[k]['cn0_dbhz'])
                grow.append(nf[k]['sigma_code_m'] / base[k]['sigma_code_m'])
            else:
                lost += 1
    drops = np.array(drops)
    assert drops.min() > -1e-9                              # nikad ne pomaže
    assert np.mean(drops > 3.0) > 0.05 and drops.max() > 8.0
    assert np.mean(grow) > 1.2


def test_nominal_mai_is_small():
    rng = np.random.default_rng(3)
    con = MultiGNSSConstellation(rng=rng)
    con.update_all(50.0)
    rx = np.array(lla_to_ecef(*ZAGREB))
    base = _cn0_by_id(MeasurementModel(rx, rng=np.random.default_rng(1)), con, 50.0)
    nominal = {s.sat_id: s for s in con.satellites}
    for k, m in base.items():
        cn0_nom = sm.cn0_dbhz(nominal[k].current_pos, rx, "L1")[0]
        assert 0.0 <= cn0_nom - m['cn0_dbhz'] < 2.0      # MAI jednako jakih: < 2 dB


def test_jamming_reduces_tracked_satellites_through_signal():
    rng = np.random.default_rng(2)
    con = WalkerDeltaConstellation(rng=rng)
    con.update_all(10.0)
    rx = np.array(lla_to_ecef(*ZAGREB))
    counts, cn0_ref = [], None
    for jn in (0.0, 5.0, 10.0, 14.0, 17.0, 20.0, 25.0):
        mm = MeasurementModel(rx, rng=np.random.default_rng(0))
        mm.jammer_jn_db = jn
        sigs = mm.build(con, 10.0)
        counts.append(mm.n_locked)
        if jn == 0.0:
            cn0_ref = {m['sat_id']: m['cn0_dbhz'] for m in sigs}
        elif jn == 10.0:
            # preživjelima C/N0 pada za 10·log10(1 + J/N) termalnog dijela
            for m in sigs:
                # (malo manje kad MAI već nosi dio šumnog poda)
                assert 9.0 < cn0_ref[m['sat_id']] - m['cn0_dbhz'] <= 10 * np.log10(11.0) + 1e-9
        for m in sigs:
            assert m['cn0_dbhz'] >= sm.TRACK_THRESHOLD_DBHZ
    assert all(a >= b for a, b in zip(counts, counts[1:]))   # monotono pada
    assert counts[0] >= 8 and counts[-1] == 0
    assert 0 < counts[4] < counts[0]                          # postupni gubitak (slabi prvi)


def test_rtk_drops_jammed_satellites():
    from web.backend.sim_session import SimSession
    s = SimSession(seed=1)
    s.set_receiver(45.815, 15.982, 120.0)
    s.set_rtk(True)
    for _ in range(3):
        s.advance(1.0)
    assert s.rtk.n_common >= 5
    s.set_attack({"type": "jamming", "js_db": 40.0, "start": s.sim_time, "end": s.sim_time + 1.0})
    for _ in range(3):
        s.advance(1.0)
    assert s.rtk.n_common == 0 and len(s.tracked_ids) == 0


def test_signal_model_is_cheaper_than_legacy_fft_channel():
    """Čuvar performansi (relativno, neovisno o stroju): signalni dio epohe novog
    modela (C/N0 + MAI za sve vidljive, DLL pristranost za 10 kanala × 2 banda) ne
    smije biti skuplji od starog FFT kanala (20 × simulate_channel) po epohi."""
    rng = np.random.default_rng(4)
    con = MultiGNSSConstellation(rng=rng)
    con.update_all(0.0)
    rx = np.array(lla_to_ecef(*ZAGREB))
    vis = [s for s in con.satellites if sm.cn0_dbhz(s.current_pos, rx)[0] > 30.0]
    ids = [s.sat_id for s in vis]
    pos = np.array([s.current_pos for s in vis])
    ranges = np.linalg.norm(pos - rx, axis=1)
    dop = np.random.default_rng(0).uniform(-4000, 4000, len(vis))

    def new_epoch(t):
        for band, attr in (("L1", "prn_code_l1"), ("L2", "prn_code_l2")):
            bank = sm.ChannelBank(ids, [getattr(s, attr) for s in vis], ranges, dop,
                                  sm.cn0_dbhz(pos, rx, band))
            bank.effective_cn0(0.0)
            for i in range(10):
                bank.code_bias_m(i, t, mp=(5.0, 0.1), mp_scale=0.5)

    def old_epoch(_t):
        for s in vis[:10]:
            for code in (s.prn_code_l1, s.prn_code_l2):
                sp.simulate_channel(code, 2.1e7, snr_db=-2, rng=rng, elev_rad=0.5, mp=(5.0, 0.1))

    def med(fn):
        fn(0.0)
        ts = []
        for k in range(7):
            t0 = time.perf_counter()
            fn(float(k))
            ts.append(time.perf_counter() - t0)
        return float(np.median(ts))

    t_new, t_old = med(new_epoch), med(old_epoch)
    assert t_new < 1.2 * t_old, f"signalni model {t_new*1e3:.1f} ms vs FFT {t_old*1e3:.1f} ms"
