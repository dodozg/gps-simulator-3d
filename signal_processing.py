import numpy as np
from physics_engine import C

# Konfiguracija simuliranog PRN signala
# U pravom GPS-u C/A kod ima 1023 čipa. Koristimo 1024 radi bržeg FFT-a.
PRN_LENGTH = 1024
CHIP_RATE = 1.023e6 # 1.023 MHz
CODE_PERIOD = PRN_LENGTH / CHIP_RATE # ~1 ms
METERS_PER_CHIP = C / CHIP_RATE # ~293 metra

# Naduzorkovanje korelacije. Bez njega je korelacija uzorkovana na 1 uzorak po
# čipu (~293 m), pa parabolička interpolacija oko vrha daje tek ~0.1 čipa (~27 m)
# preciznosti — to je bio dominantni izvor greške pozicije (real GPS ranging je
# metarski). S OVERSAMPLE uzoraka po čipu razlučivost je ~293/OS m, pa ranging
# padne na par metara. Trošak: FFT nad PRN_LENGTH*OS uzoraka (samo za ~10
# odabranih satelita po epohi).
OVERSAMPLE = 8
METERS_PER_SAMPLE = METERS_PER_CHIP / OVERSAMPLE   # ~36.6 m
SAMPLES = PRN_LENGTH * OVERSAMPLE

# Multipath (odraz od tla/zgrada): zakašnjela, prigušena kopija signala. Kodni
# multipath UVIJEK kasni (pozitivan bias) pa ga filtar ne može usrednjiti na
# nulu — glavni je izvor i pristranosti i "trzanja" rješenja. Vrijednosti
# predstavljaju REZIDUAL nakon mitigacije u prijemniku (uski korelator i sl.);
# skaliraju se dodatno po elevaciji (jače pri horizontu).
MP_DIST_MIN, MP_DIST_MAX = 1.0, 12.0    # [m] dodatni put reflektiranog signala
MP_ATT_MIN, MP_ATT_MAX = 0.03, 0.15     # prigušenje odraza (rezidual po mitigaciji)


def sample_multipath(rng):
    """Nasumična geometrija odraza za JEDAN satelit/epohu — DIJELI se između L1 i L2.

    Multipath potječe od iste fizičke geometrije odraza (isti dodatni put, isti
    reflektor), pa je kodna greška na L1 i L2 visoko KORELIRANA, ne nezavisna.
    Zato se draw radi jednom po satelitu i prosljeđuje objema frekvencijama
    (`simulate_rf_channel(..., mp=...)`); jedina preostala L1/L2 razlika je različit
    PRN kod (proxy za stvarne kodno/fazne razlike po frekvenciji).

    Ranije su L1 i L2 vukli NEZAVISAN multipath: iono-free kombinacija
    (koeficijenti f1²/(f1²−f2²)≈2.55 i f2²/(f1²−f2²)≈1.55) nekorelirani multipath
    napuhava ~√(2.55²+1.55²)≈3×, dok korelirani (zajednički) uglavnom prolazi
    koeficijentom ≈1 — pa je iono-free "predodavao" šum koji fizika ne stvara.

    Vraća (extra_dist [m], att_raw) — att_raw je prigušenje PRIJE elevacijskog
    skaliranja (mp_scale se računa iz elevacije unutar kanala).
    """
    extra_dist = rng.uniform(MP_DIST_MIN, MP_DIST_MAX)
    att_raw = rng.uniform(MP_ATT_MIN, MP_ATT_MAX)
    return (extra_dist, att_raw)

def generate_prn(sat_id):
    """Generira pseudo-slučajni niz (PRN) specifičan za svaki satelit."""
    # Hashiranje ID-ja za deterministički seed
    seed = sum(ord(c) for c in sat_id) * 12345
    rng = np.random.RandomState(seed % (2**32))
    # Generiranje niza od -1 i 1 (1 vrijednost po čipu)
    return rng.choice([-1.0, 1.0], size=PRN_LENGTH)

def _upsample(prn):
    """Čipovi -> uzorci: OVERSAMPLE identičnih uzoraka po čipu."""
    return np.repeat(prn, OVERSAMPLE)

def ideal_pseudorange(distance, iono_delay_meters):
    """Savršeno mjerenje dometa: bez multipath-a, AWGN-a i korelatorske kvantizacije.

    Zaobilazi cijeli RF lanac (simulate_rf_channel + decode_signal) i vraća točnu
    kašnjenjem-produljenu udaljenost. Koristi se u ideal (zero-noise) modu da se
    izolira KONZISTENTNOST modela: svaki član koji prijemnik korigira mora imati
    egzaktno odgovarajući član ubrizgan u mjerenje (npr. Sagnac). Sve što preostane
    iznad ~mm je nekonzistentnost injekcije↔korekcije, ne mjerni šum.
    """
    return distance + iono_delay_meters


def simulate_rf_channel(prn, distance, iono_delay_meters, snr_db=-10, rng=None, elev_rad=None, mp=None):
    """
    Simulira prolazak signala kroz prostor i atmosferu.
    Pravi signal je kontinuiran. Mi ovdje simuliramo "prozor" koji prijemnik hvata.
    rng: np.random.Generator za multipath/AWGN (None -> svjež default_rng).
    elev_rad: elevacija satelita — multipath je jači pri niskoj elevaciji
              (otvoreno nebo/zenit ~ par m). None -> srednja vrijednost.
    mp: (extra_dist, att_raw) dijeljena geometrija odraza (vidi `sample_multipath`)
        da L1 i L2 dobiju KORELIRAN multipath. None -> draw interno (nekorelirano,
        stari put). AWGN ostaje nezavisan po pozivu (različiti RF lanci).
    """
    if rng is None:
        rng = np.random.default_rng()
    total_delay_meters = distance + iono_delay_meters

    # Koliko cijelih PRN kodova je stalo u udaljenost (Integer Ambiguity)
    # Prijemnik ovo inače rješava kroz navigacijsku poruku
    code_length_meters = PRN_LENGTH * METERS_PER_CHIP
    integer_blocks = int(total_delay_meters // code_length_meters)

    # Ostatak udaljenosti koji mjerimo korelacijom (sub-millisecond), u UZORCIMA.
    remainder_meters = total_delay_meters % code_length_meters
    shift_samples = remainder_meters / METERS_PER_SAMPLE

    # Precizan frakcijski pomak u frekvencijskoj domeni (shift theorem).
    prn_s = _upsample(prn)
    fft_prn = np.fft.fft(prn_s)
    freqs = np.fft.fftfreq(SAMPLES)
    shifted_signal = np.real(np.fft.ifft(fft_prn * np.exp(-1j * 2 * np.pi * freqs * shift_samples)))

    # Multipath: zakašnjela, prigušena kopija (odbijanje od tla/zgrada). Jačina
    # ovisi o elevaciji — pri zenitu je nema gotovo nikako, pri horizontu je puna.
    if elev_rad is None:
        mp_scale = 0.5
    else:
        s = max(float(np.sin(elev_rad)), 0.05)
        mp_scale = float(np.clip(0.1 + 0.9 * (1.0 - s), 0.1, 1.0))
    # Dijeljena geometrija odraza (L1/L2 korelirano) ako je predana, inače draw.
    if mp is None:
        multipath_extra_dist = rng.uniform(MP_DIST_MIN, MP_DIST_MAX)
        att_raw = rng.uniform(MP_ATT_MIN, MP_ATT_MAX)
    else:
        multipath_extra_dist, att_raw = mp
    multipath_attenuation = att_raw * mp_scale
    mp_total_delay = total_delay_meters + multipath_extra_dist
    mp_shift_samples = (mp_total_delay % code_length_meters) / METERS_PER_SAMPLE
    mp_signal = np.real(np.fft.ifft(fft_prn * np.exp(-1j * 2 * np.pi * freqs * mp_shift_samples))) * multipath_attenuation

    combined_signal = shifted_signal + mp_signal

    # Dodavanje AWGN (šuma)
    signal_power = np.mean(combined_signal**2)
    noise_power = signal_power / (10 ** (snr_db / 10))
    noise = rng.normal(0, np.sqrt(noise_power), SAMPLES)

    received_signal = combined_signal + noise
    return received_signal, integer_blocks

def decode_signal(received_signal, local_prn, integer_blocks):
    """
    Prijemnik dekodira signal tražeći korelacijski vrh (Peak).
    """
    local_s = _upsample(local_prn)
    # Križna korelacija pomoću FFT-a
    correlation = np.real(np.fft.ifft(np.fft.fft(received_signal) * np.conj(np.fft.fft(local_s))))

    # Traženje vrha (maksimalne podudarnosti)
    peak_idx = int(np.argmax(correlation))

    # Sub-uzorak preciznost paraboličnom interpolacijom oko vrha.
    if 0 < peak_idx < SAMPLES - 1:
        y1 = correlation[peak_idx - 1]
        y2 = correlation[peak_idx]
        y3 = correlation[peak_idx + 1]
        denom = (y1 - 2 * y2 + y3)
        sub_chip_offset = (y1 - y3) / (2 * denom) if denom != 0 else 0.0
        peak_exact = peak_idx + sub_chip_offset
    else:
        peak_exact = float(peak_idx)

    # Rekonstrukcija izmjerene pseudoudaljenosti
    code_length_meters = PRN_LENGTH * METERS_PER_CHIP
    measured_distance = (integer_blocks * code_length_meters) + (peak_exact * METERS_PER_SAMPLE)
    return measured_distance
