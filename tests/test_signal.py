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
