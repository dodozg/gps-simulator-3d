"""DSP jezgra: generiranje PRN kodova i FFT korelacija."""
import numpy as np

import signal_processing as sp


def test_prn_is_deterministic_and_bipolar():
    a = sp.generate_prn("SAT_1_2_L1")
    b = sp.generate_prn("SAT_1_2_L1")
    np.testing.assert_array_equal(a, b)  # isti ID -> isti kod
    assert set(np.unique(a)).issubset({-1.0, 1.0})
    assert len(a) == sp.PRN_LENGTH


def test_prn_autocorrelation_peaks_at_zero():
    prn = sp.generate_prn("SAT_3_1_L1")
    corr = np.real(np.fft.ifft(np.fft.fft(prn) * np.conj(np.fft.fft(prn))))
    assert np.argmax(corr) == 0
    # Auto-vrh mora nadmašiti cross-korelaciju s drugim satelitom.
    other = sp.generate_prn("SAT_4_2_L1")
    cross = np.real(np.fft.ifft(np.fft.fft(prn) * np.conj(np.fft.fft(other))))
    assert corr.max() > 5 * np.abs(cross).max()


def test_gold_codes_have_bounded_three_valued_crosscorr():
    """Pravi C/A Gold kodovi (ne random ±1): garantirano OMEĐENA troznačna
    cross-korelacija {-65, -1, 63} (preferirani par, n=10) i autokorelacija s
    vrhom 1023 i pobočnim maksimumom 65. To je svojstvo koje random ±1 nema
    (cross ~√1023, neomeđeno) — temelj za razdvajanje satelita u kombiniranom
    signalu (§19.1).
    """
    def circ(a, b):
        return np.rint(np.real(np.fft.ifft(np.fft.fft(a) * np.conj(np.fft.fft(b))))).astype(int)

    c0, c5, c100 = sp.gold_code(0), sp.gold_code(5), sp.gold_code(100)
    assert len(c0) == 1023 and set(np.unique(c0)).issubset({-1.0, 1.0})
    auto = circ(c0, c0)
    assert auto[0] == 1023
    assert np.abs(auto[1:]).max() == 65                      # pobočni maksimum omeđen
    for other in (c5, c100):
        assert set(np.unique(circ(c0, other))).issubset({-65, -1, 63})
    # generate_prn vraća Gold kod, deterministički po sat_id
    assert np.array_equal(sp.generate_prn("SAT_X_L1"), sp.generate_prn("SAT_X_L1"))


def test_multipath_is_correlated_across_frequencies():
    """Dijeljena geometrija odraza (`sample_multipath` -> `mp=`) mora dati VISOKO
    korelirani L1/L2 multipath, pa iono-free kombinacija NE napuhava multipath ~3×
    (kao kod nezavisnog draw-a). Fizikalni realizam: odraz je ista geometrija za obje
    frekvencije. Regresijski čuvar da se L1/L2 multipath ne vrati na nezavisan.
    """
    f1, f2 = 1575.42e6, 1227.60e6
    c1 = f1**2 / (f1**2 - f2**2)
    c2 = f2**2 / (f1**2 - f2**2)
    prn1 = sp.generate_prn("SAT_9_9_L1")
    prn2 = sp.generate_prn("SAT_9_9_L2")
    d = 22_000_000.0
    elev = np.radians(30.0)

    def trials(shared, n=140):
        rng = np.random.default_rng(3)
        e1, e2, eif = [], [], []
        for _ in range(n):
            mp = sp.sample_multipath(rng)
            rx1, b1 = sp.simulate_rf_channel(prn1, d, 0.0, snr_db=40, rng=rng,
                                             elev_rad=elev, mp=(mp if shared else None))
            rx2, b2 = sp.simulate_rf_channel(prn2, d, 0.0, snr_db=40, rng=rng,
                                             elev_rad=elev, mp=(mp if shared else None))
            m1 = sp.decode_signal(rx1, prn1, b1) - d
            m2 = sp.decode_signal(rx2, prn2, b2) - d
            e1.append(m1); e2.append(m2); eif.append(c1 * m1 - c2 * m2)
        e1, e2, eif = np.array(e1), np.array(e2), np.array(eif)
        return np.corrcoef(e1, e2)[0, 1], eif.std()

    corr_indep, std_if_indep = trials(shared=False)
    corr_shared, std_if_shared = trials(shared=True)

    assert corr_shared > 0.9, f"dijeljeni multipath nije koreliran: corr={corr_shared:.3f}"
    assert abs(corr_indep) < 0.3, f"nezavisni multipath ne bi smio korelirati: corr={corr_indep:.3f}"
    # Korelirani prolazi iono-free ~1×, nezavisni ~3× -> barem 2× manji std.
    assert std_if_shared < 0.5 * std_if_indep, (
        f"iono-free multipath std nije pao: {std_if_shared:.3f} vs {std_if_indep:.3f}"
    )


def test_channel_decode_recovers_range_order():
    prn = sp.generate_prn("SAT_0_0_L1")
    true_dist = 22_000_000.0  # ~22 000 km, tipična GPS udaljenost
    rx, blocks = sp.simulate_rf_channel(prn, distance=true_dist,
                                        iono_delay_meters=0.0, snr_db=10)
    measured = sp.decode_signal(rx, prn, blocks)
    # Multipath (10-100 m) i šum unose pristranost, ali mjerenje mora pasti
    # unutar jednog PRN bloka (~300 km) od prave udaljenosti.
    code_len = sp.PRN_LENGTH * sp.METERS_PER_CHIP
    assert abs(measured - true_dist) < code_len
    assert measured > 0
