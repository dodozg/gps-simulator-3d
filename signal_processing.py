import numpy as np
from physics_engine import C

# Konfiguracija PRN signala. Pravi GPS C/A kod ima 1023 čipa (period točno 1 ms).
# Ranije smo koristili 1024 (potencija dvojke) radi bržeg FFT-a uz RANDOM ±1 niz;
# sada koristimo PRAVE C/A Gold kodove (vidi gold_code) pa je duljina 1023. FFT nad
# 1023·OVERSAMPLE nije potencija dvojke (faktor 31) pa je ~2× sporiji, ali cache
# FFT-ova lokalnih kodova to nadoknađuje (vidi _fft_upsampled).
PRN_LENGTH = 1023
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

def _m_sequence(taps):
    """10-bitni Fibonacci LFSR -> m-niz maksimalne duljine 1023 (bitovi 0/1).

    `taps` su pozicije povratne veze (1..10) prema karakterističnom polinomu.
    Registar starta u svim jedinicama (standardni C/A početni uvjet).
    """
    reg = np.ones(10, dtype=np.int8)
    seq = np.empty(PRN_LENGTH, dtype=np.int8)
    for i in range(PRN_LENGTH):
        seq[i] = reg[9]                       # izlaz = zadnji bit registra
        fb = 0
        for tp in taps:
            fb ^= int(reg[tp - 1])
        reg[1:] = reg[:-1]                    # pomak
        reg[0] = fb
    return seq


# Preferirani par m-nizova iz GPS ICD-a (generira C/A Gold obitelj):
#   G1: 1 + x^3 + x^10          G2: 1 + x^2 + x^3 + x^6 + x^8 + x^9 + x^10
_G1 = _m_sequence([3, 10])
_G2 = _m_sequence([2, 3, 6, 8, 9, 10])


def gold_code(shift):
    """C/A Gold kod: G1 XOR ciklički-pomaknuti G2, kao ±1 niz duljine 1023.

    `shift` (0..1022) bira člana Gold obitelji (u pravom C/A to je odabir faze G2
    po PRN broju). Za razliku od random ±1 niza, Gold kodovi imaju GARANTIRANO
    omeđenu troznačnu cross-korelaciju {-65, -1, 63} (preferirani par, n=10) —
    zato se u kombiniranom signalu slabiji satelit ne utopi u jačem (vidi §19.1).
    """
    bits = _G1 ^ np.roll(_G2, int(shift) % PRN_LENGTH)
    return 1.0 - 2.0 * bits.astype(np.float64)   # 0 -> +1, 1 -> -1


def _prn_shift(sat_id):
    """Deterministički sat_id -> faza Gold koda (FNV-1a, reproducibilno bez ovisnosti
    o PYTHONHASHSEED). Prostor od 1023 kodova >> broj potrebnih (~192), pa su
    kolizije rijetke (a i realni GPS ponavlja PRN-ove među sustavima)."""
    h = 2166136261
    for c in sat_id:
        h = ((h ^ ord(c)) * 16777619) & 0xFFFFFFFF
    return h % PRN_LENGTH


def generate_prn(sat_id):
    """PRN za satelit = pravi C/A Gold kod (faza deterministički odabrana po sat_id)."""
    return gold_code(_prn_shift(sat_id))

def _upsample(prn):
    """Čipovi -> uzorci: OVERSAMPLE identičnih uzoraka po čipu."""
    return np.repeat(prn, OVERSAMPLE)


# --- Per-satelitski RF kanal (frekvencijska domena, brzo) --------------------
# FFT (naduzorkovanog) koda je konstantan po satelitu/bandu pa se cachira — to je
# ključni ubrzavač uz 1023-dužinu (ne-potencija dvojke, ~2× sporiji FFT). Kanal
# gradimo i dekodiramo IZRAVNO u frekvencijskoj domeni: korelacija koda sa samim
# sobom je |FFT|² (keširano), pa se izbjegava među-buffer i njegovi transformi
# (4 → 2 transforma po satelitu/bandu). Vidi simulate_channel.
_FREQS = np.fft.fftfreq(SAMPLES)
_fft_cache = {}
_pw_cache = {}


def _fft_upsampled(prn):
    """FFT naduzorkovanog koda, keširan (kodovi su konstantni po satelitu/bandu)."""
    key = prn.tobytes()
    f = _fft_cache.get(key)
    if f is None:
        f = np.fft.fft(_upsample(prn))
        _fft_cache[key] = f
    return f


def _power_spectrum(prn):
    """|FFT(naduzorkovani kod)|² (auto-korelacija koda u frek. domeni), keširano."""
    key = prn.tobytes()
    p = _pw_cache.get(key)
    if p is None:
        f = _fft_upsampled(prn)
        p = (f * np.conj(f)).real
        _pw_cache[key] = p
    return p


def _code_blocks(total_delay_meters):
    """(cijeli kodni periodi, frakcijski pomak u uzorcima) za dani domet."""
    code_len = PRN_LENGTH * METERS_PER_CHIP
    return int(total_delay_meters // code_len), (total_delay_meters % code_len) / METERS_PER_SAMPLE


def _peak_range(correlation, integer_blocks):
    """Parabolička sub-uzorak interpolacija vrha korelacije -> izmjereni domet [m]."""
    peak_idx = int(np.argmax(correlation))
    if 0 < peak_idx < SAMPLES - 1:
        y1, y2, y3 = correlation[peak_idx - 1], correlation[peak_idx], correlation[peak_idx + 1]
        denom = y1 - 2 * y2 + y3
        peak_exact = peak_idx + ((y1 - y3) / (2 * denom) if denom != 0 else 0.0)
    else:
        peak_exact = float(peak_idx)
    return integer_blocks * (PRN_LENGTH * METERS_PER_CHIP) + peak_exact * METERS_PER_SAMPLE


def simulate_channel(prn, total_delay_meters, snr_db=-2, rng=None, elev_rad=None, mp=None):
    """Per-satelitski RF kanal + dekodiranje, cijelo u frekvencijskoj domeni.

    Ekvivalentno: izgradi primljeni signal (direktni + zakašnjeli multipath + AWGN)
    pa ga koreliraj s lokalnim kodom — ali bez među-buffera. Signal se korelira sam
    sa sobom pa je to |FFT_koda|² (keširano) pomnoženo faznim rampama pomaka; šum se
    doda u frek. domeni (FFT bijelog šuma). Ostaje samo JEDAN fft (šum) + JEDAN ifft.
    Vrati izmjereni domet [m].
    """
    if rng is None:
        rng = np.random.default_rng()
    fft_prn = _fft_upsampled(prn)
    pw = _power_spectrum(prn)
    integer_blocks, shift = _code_blocks(total_delay_meters)
    spec = pw * np.exp(-1j * 2 * np.pi * _FREQS * shift)          # direktni signal (već korel'iran)
    if mp is not None:
        extra, att_raw = mp
        mp_scale = 0.5 if elev_rad is None else float(np.clip(0.1 + 0.9 * (1.0 - max(float(np.sin(elev_rad)), 0.05)), 0.1, 1.0))
        _, mp_shift = _code_blocks(total_delay_meters + extra)
        spec = spec + (att_raw * mp_scale) * pw * np.exp(-1j * 2 * np.pi * _FREQS * mp_shift)
    # Termalni šum: korelacija bijelog šuma s kodom = ifft(FFT_šuma · conj(FFT_koda)).
    # SNR (pred-despreading) je relativan na snagu signala (amp≈1), kao u starom modelu.
    noise_power = 1.0 / (10 ** (snr_db / 10))
    fft_noise = np.fft.fft(rng.normal(0, np.sqrt(noise_power), SAMPLES))
    corr = np.real(np.fft.ifft(spec + fft_noise * np.conj(fft_prn)))
    return _peak_range(corr, integer_blocks)

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

    # Precizan frakcijski pomak u frekvencijskoj domeni (shift theorem). FFT koda
    # je keširan (konstantan po satelitu) — ključno uz 1023-dužinu (ne-potencija 2).
    fft_prn = _fft_upsampled(prn)
    freqs = _FREQS
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
    """Dekodira JEDAN izolirani kanal (stari per-sat put; koristi se u testovima).

    Kombinirani lanac koristi `decode_from_combined` (dijeli precomputan FFT).
    """
    correlation = np.real(np.fft.ifft(np.fft.fft(received_signal) * np.conj(_fft_upsampled(local_prn))))
    return _peak_range(correlation, integer_blocks)
