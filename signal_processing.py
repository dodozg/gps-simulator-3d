import numpy as np
from physics_engine import C

# Konfiguracija simuliranog PRN signala
# U pravom GPS-u C/A kod ima 1023 čipa. Koristimo 1024 radi bržeg FFT-a.
PRN_LENGTH = 1024
CHIP_RATE = 1.023e6 # 1.023 MHz
CODE_PERIOD = PRN_LENGTH / CHIP_RATE # ~1 ms
METERS_PER_CHIP = C / CHIP_RATE # ~293 metra

def generate_prn(sat_id):
    """Generira pseudo-slučajni niz (PRN) specifičan za svaki satelit."""
    # Hashiranje ID-ja za deterministički seed
    seed = sum(ord(c) for c in sat_id) * 12345
    rng = np.random.RandomState(seed % (2**32))
    # Generiranje niza od -1 i 1
    return rng.choice([-1.0, 1.0], size=PRN_LENGTH)

def simulate_rf_channel(prn, distance, iono_delay_meters, snr_db=-10, rng=None):
    """
    Simulira prolazak signala kroz prostor i atmosferu.
    Pravi signal je kontinuiran. Mi ovdje simuliramo "prozor" koji prijemnik hvata.
    rng: np.random.Generator za multipath/AWGN (None -> svjež default_rng).
    """
    if rng is None:
        rng = np.random.default_rng()
    total_delay_meters = distance + iono_delay_meters
    
    # Koliko cijelih PRN kodova je stalo u udaljenost (Integer Ambiguity)
    # Prijemnik ovo inače rješava kroz navigacijsku poruku
    code_length_meters = PRN_LENGTH * METERS_PER_CHIP
    integer_blocks = int(total_delay_meters // code_length_meters)
    
    # Ostatak udaljenosti koji moramo mjeriti korelacijom (Sub-millisecond)
    remainder_meters = total_delay_meters % code_length_meters
    
    # Pretvaranje udaljenosti u pomak u "čipovima" (indeksima polja)
    shift_chips = remainder_meters / METERS_PER_CHIP
    
    # Interpolacija pomaka (jer shift ne mora biti cijeli broj)
    # Za simulaciju ćemo koristiti zaokruživanje i sub-chip interpolaciju 
    # ili jednostavno pomicanje faze u frekvencijskoj domeni.
    # Koristimo frekvencijsku domenu za precizan frakcijski pomak:
    fft_prn = np.fft.fft(prn)
    freqs = np.fft.fftfreq(PRN_LENGTH)
    # Shift theorem: F(k) * exp(-i * 2*pi * k * shift / N)
    shifted_fft = fft_prn * np.exp(-1j * 2 * np.pi * freqs * shift_chips)
    shifted_signal = np.real(np.fft.ifft(shifted_fft))
    
    # Multipath simulacija: Zakašnjela i prigušena kopija signala (odbijanje od tla/zgrada)
    # Dodatno kašnjenje od 10 do 100 metara
    multipath_extra_dist = rng.uniform(10.0, 100.0)
    multipath_attenuation = rng.uniform(0.2, 0.6) # Prigušenje (20% do 60% originalne amplitude)
    
    mp_total_delay = total_delay_meters + multipath_extra_dist
    mp_shift_chips = (mp_total_delay % code_length_meters) / METERS_PER_CHIP
    mp_shifted_fft = fft_prn * np.exp(-1j * 2 * np.pi * freqs * mp_shift_chips)
    mp_signal = np.real(np.fft.ifft(mp_shifted_fft)) * multipath_attenuation
    
    # Kombiniranje direktnog i reflektiranog signala
    combined_signal = shifted_signal + mp_signal
    
    # Dodavanje AWGN (šuma)
    signal_power = np.mean(combined_signal**2)
    noise_power = signal_power / (10 ** (snr_db / 10))
    noise = rng.normal(0, np.sqrt(noise_power), PRN_LENGTH)
    
    received_signal = combined_signal + noise
    
    return received_signal, integer_blocks

def decode_signal(received_signal, local_prn, integer_blocks):
    """
    Prijemnik dekodira signal tražeći korelacijski vrh (Peak).
    """
    # Križna korelacija pomoću FFT-a
    fft_rx = np.fft.fft(received_signal)
    fft_local = np.fft.fft(local_prn)
    
    # ifft( FFT(rx) * conj(FFT(local)) )
    correlation = np.real(np.fft.ifft(fft_rx * np.conj(fft_local)))
    
    # Traženje vrha (maksimalne podudarnosti)
    peak_idx = np.argmax(correlation)
    
    # Da bismo dobili sub-chip preciznost, radimo paraboličnu interpolaciju oko vrha
    if peak_idx > 0 and peak_idx < PRN_LENGTH - 1:
        y1 = correlation[peak_idx - 1]
        y2 = correlation[peak_idx]
        y3 = correlation[peak_idx + 1]
        # Vrh parabole
        sub_chip_offset = (y1 - y3) / (2 * (y1 - 2*y2 + y3))
        peak_exact = peak_idx + sub_chip_offset
    else:
        peak_exact = float(peak_idx)
        
    # Rekonstrukcija izmjerene pseudoudaljenosti
    # Udaljenost = (cijeli blokovi * duljina koda) + (izmjeren pomak * metara_po_čipu)
    measured_distance = (integer_blocks * PRN_LENGTH * METERS_PER_CHIP) + (peak_exact * METERS_PER_CHIP)
    
    return measured_distance
