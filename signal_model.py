"""Fizikalni signalni model prijemnika: link budget → C/N0, korelatori, DLL šum.

Zamjenjuje raniji "snapshot" RF kanal (FFT korelacija 1 ms signala uz fiksni
SNR = −2 dB) u živom mjernom lancu. Umjesto da generira uzorke signala, model radi
na RAZINI KORELATORA (polu-analitički), što je i brže i fizikalno vjernije:

1. **Link budget → C/N0** po satelitu i bandu (`cn0_dbhz`): primljena snaga na
   referentnoj udaljenosti, skaliranje udaljenošću (slobodni prostor, 1/d²),
   oblikovani snop satelitske antene (rub Zemlje +2 dB), atmosfersko gušenje,
   dijagram antene prijemnika (pad prema horizontu) i šumni pod N0 = k·T_sys uz
   noise figure i implementacijske gubitke.

2. **Ometač (jamming) i MAI** podižu efektivni šumni pod:
       1/(C/N0)_eff = 1/(C/N0) + (J/N)·B_fe/(Q·Rc)/(C/N0) + Σ_k (C_k/C)·κ_k
   (Betz; spektralni koeficijent razdvajanja). Za širokopojasni šumni ometač
   Q = 2 i B_fe = 2·Rc pa je faktor točno 1: (C/N0)_eff = C/N0 − 10·log10(1 + J/N).
   κ_k je snaga cross-korelacije satelita k koja PROĐE koherentnu integraciju T:
       κ_k = T · ⟨X²⟩ · Σ_m sinc²(π·(Δf_k − m·1 kHz)·T)
   (C/A kod je periodičan 1 ms → linijski spektar s razmakom 1 kHz; integracija
   preko T je sinc filtar širine ~1/T oko svake linije). Usrednjeno po Doppleru
   to daje poznatih −61,8 dB/Hz za C/A na C/A; za konkretan par ovisi o relativnom
   Doppleru i T — to je potiskivanje cross-korelacije koje 1 ms snapshot nema.

3. **Praćenje koda (DLL)**: rani-kasni korelator s razmakom d. Pristranost
   (deterministička) dolazi iz diskriminatora: multipath (dvozračni model,
   ε = α·δ/(1+α) za kratka kašnjenja) + KOHERENTNA cross-korelacija jačih
   satelita (pravi Gold kodovi, Doppler-pomaknuti bin, × sinc(π·δ·T) × odziv
   petlje na otkucaj δ). Termalni šum slijedi standardnu formulu za nekoherentni
   EMLP diskriminator (Betz & Kolodziejski; Kaplan & Hegarty):
       σ² [čip²] = B_L·d / (2·C/N0) · (1 + 2 / ((2 − d)·T·C/N0))
   Ispod praga C/N0 (`TRACK_THRESHOLD_DBHZ`) prijemnik gubi zabravu.

Svi parametri su dokumentirani ispod; ništa ne ovisi o scipy-ju (samo numpy).
"""
import numpy as np

from physics_engine import C
import signal_processing as sp

# --- Link budget ---------------------------------------------------------------
K_BOLTZMANN_DBW = -228.6        # [dBW/K/Hz] 10·log10(k)
T_ANT_K = 130.0                 # [K] šumna temperatura antene (nebo + tlo)
NOISE_FIGURE_DB = 2.0           # [dB] LNA + front-end
IMPL_LOSS_DB = 2.0              # [dB] kvantizacija, filtriranje, korelatorski gubici
T0_K = 290.0
# N0 = k·(T_ant + T0·(F − 1)) ≈ −203,8 dBW/Hz
N0_DBW_HZ = K_BOLTZMANN_DBW + 10.0 * np.log10(T_ANT_K + T0_K * (10 ** (NOISE_FIGURE_DB / 10) - 1.0))

# Primljena snaga u izotropnu antenu (0 dBic) na referentnoj udaljenosti R_REF.
# L1 C/A: ICD minimum je −158,5 dBW, izmjerene vrijednosti modernih blokova su
# ~3 dB iznad (−155,5). L2 (P(Y)/L2C) je ~3 dB slabiji. Svi sustavi u simulatoru
# dijele isti model signala (pojednostavljenje, vidi dokumentaciju §5.1).
P_REF_DBW = {"L1": -155.5, "L2": -158.5}
R_REF_M = 20200e3                # [m] referentna udaljenost (GPS u zenitu)
SAT_EDGE_GAIN_DB = 2.0           # oblikovani snop: +2 dB na rubu Zemlje (kompenzira dulji put)
ATM_LOSS_ZENITH_DB = 0.035       # [dB] atmosfersko gušenje u zenitu (× 1/sin(el))

# Antena prijemnika (patch, RHCP): G(el) = G_ZENITH + 10·ANT_Q·log10(sin el),
# tj. +3 dBic u zenitu, ~0 dBic na 30°, ~−4,5 dBic na 10°, ~−7 dBic na 5°.
ANT_GAIN_ZENITH_DBIC = 3.0
ANT_Q = 0.95
ANT_MIN_SIN = 0.05

# --- Ometač --------------------------------------------------------------------
JAM_SSC_FACTOR = 1.0             # B_fe/(Q·Rc): širokopojasni šum, Q = 2, B_fe = 2,046 MHz

# --- Korelator / petlje --------------------------------------------------------
T_COH_S = 0.020                  # [s] koherentna integracija (= trajanje bita poruke)
DLL_BL_HZ = 2.0                  # [Hz] šumna širina DLL petlje (bez nosive pomoći)
DLL_SPACING_CHIPS = 0.5          # rani-kasni razmak d [čip]
TRACK_THRESHOLD_DBHZ = 28.0      # prag zabrave (PLL/DLL) za T = 20 ms
LINE_SPACING_HZ = 1.0 / sp.CODE_PERIOD   # 1 kHz — razmak spektralnih linija C/A koda
X_MS = (2.0 / 3.0) / sp.PRN_LENGTH       # ⟨X²⟩ cross-korelacije (pravokutni čipovi, slučajni pomak)
XCORR_MIN_WEIGHT = 3e-3          # |ε| ≤ w·max|ΔX|/2 ≈ 19 m·w → ispod praga pristranost < 6 cm (zanemarivo)

BANDS = ("L1", "L2")


def _db(x):
    return 10.0 * np.log10(x)


def antenna_gain_dbic(sin_el):
    """Dijagram antene prijemnika [dBic] u ovisnosti o sin(elevacije)."""
    s = np.maximum(np.asarray(sin_el, float), ANT_MIN_SIN)
    return ANT_GAIN_ZENITH_DBIC + 10.0 * ANT_Q * np.log10(s)


def cn0_dbhz(sat_pos, rx_pos, band="L1", power_offset_db=0.0):
    """Nominalni C/N0 [dB-Hz] (termalni šum, bez ometača/MAI) iz link budgeta.

    Radi i vektorski: sat_pos (N,3) → (N,). Ispod horizonta vraća −inf.
    """
    sat_pos = np.atleast_2d(np.asarray(sat_pos, float))
    rx_pos = np.asarray(rx_pos, float)
    los = sat_pos - rx_pos
    d = np.linalg.norm(los, axis=1)
    rn = np.linalg.norm(rx_pos)
    sin_el = (los @ rx_pos) / (d * rn)
    # Nadirni kut na satelitu: sin(θ) = |rx|·cos(el)/|sat|; rub Zemlje sin(θ_e) = R/|sat|.
    cos_el = np.sqrt(np.clip(1.0 - sin_el ** 2, 0.0, 1.0))
    rel = np.clip(cos_el, 0.0, 1.0)                    # (sinθ/sinθ_e) uz |rx| ≈ R
    sat_gain = SAT_EDGE_GAIN_DB * rel ** 2
    atm = ATM_LOSS_ZENITH_DB / np.maximum(sin_el, ANT_MIN_SIN)
    p = (P_REF_DBW[band] - 20.0 * np.log10(d / R_REF_M) + sat_gain - atm
         + antenna_gain_dbic(sin_el) + np.asarray(power_offset_db, float))
    out = p - N0_DBW_HZ - IMPL_LOSS_DB
    return np.where(sin_el > 0.0, out, -np.inf)


def jam_loss_db(jn_db):
    """Degradacija C/N0 [dB] od širokopojasnog ometača J/N [dB] (0 → 0 dB)."""
    if jn_db is None or jn_db <= -200:
        return 0.0
    return float(_db(1.0 + JAM_SSC_FACTOR * 10 ** (jn_db / 10.0)))


def coherent_gain(df_hz, t_coh=T_COH_S):
    """|sinc(π·Δf·T)| — amplituda interferencije na frekvencijskom pomaku Δf koja
    prođe koherentnu integraciju trajanja T (1 = bez potiskivanja)."""
    return np.abs(np.sinc(np.asarray(df_hz, float) * t_coh))   # np.sinc(x) = sin(πx)/(πx)


def mai_kappa(df_hz, t_coh=T_COH_S):
    """Efektivni spektralni koeficijent [1/Hz] cross-korelacije na rel. Doppleru Δf.

    Zbroj po dvije najbliže spektralne linije C/A koda (razmak 1 kHz). Prosjek po
    Doppleru je ⟨X²⟩/1 kHz ≈ 6,5·10⁻⁷ s = −61,9 dB/Hz (poznati C/A SSC).
    """
    df = np.asarray(df_hz, float)
    m0 = np.floor(df / LINE_SPACING_HZ)
    r0 = df - m0 * LINE_SPACING_HZ
    r1 = r0 - LINE_SPACING_HZ
    return t_coh * X_MS * (np.sinc(r0 * t_coh) ** 2 + np.sinc(r1 * t_coh) ** 2)


def effective_cn0_dbhz(cn0_db, jn_db=0.0, mai_n0_over_c=0.0):
    """Efektivni C/N0 uz ometač i MAI (dodatni N0/C [s] od cross-korelacije)."""
    cn0 = 10 ** (np.asarray(cn0_db, float) / 10.0)
    inv = (1.0 / cn0) * (1.0 + JAM_SSC_FACTOR * (10 ** (jn_db / 10.0) if jn_db else 0.0)) + mai_n0_over_c
    return -_db(inv)


def dll_sigma_chips(cn0_db, t_coh=T_COH_S, bl_hz=DLL_BL_HZ, d=DLL_SPACING_CHIPS):
    """Termalni šum koda [čip] nekoherentnog EMLP DLL-a (Betz & Kolodziejski)."""
    cn0 = 10 ** (np.asarray(cn0_db, float) / 10.0)
    var = bl_hz * d / (2.0 * cn0) * (1.0 + 2.0 / ((2.0 - d) * t_coh * cn0))
    return np.sqrt(var)


def dll_sigma_m(cn0_db, **kw):
    return dll_sigma_chips(cn0_db, **kw) * sp.METERS_PER_CHIP


def loop_gain(beat_hz, bl_hz=DLL_BL_HZ):
    """Odziv DLL petlje 1. reda na sinusnu smetnju frekvencije `beat_hz`.

    Petlja šumne širine B_L ima kutnu frekvenciju K = 4·B_L [rad/s]; smetnju koja
    rotira brže od toga usrednji (|H| = 1/√(1 + (2π·f/K)²)).
    """
    k = 4.0 * bl_hz
    return 1.0 / np.sqrt(1.0 + (2.0 * np.pi * np.asarray(beat_hz, float) / k) ** 2)


# --- Gold cross-korelacija s Doppler-binom -----------------------------------------
_N = sp.PRN_LENGTH
_n = np.arange(_N)
_bin_cache = {}


def _bin_phasor(m):
    p = _bin_cache.get(m)
    if p is None:
        p = np.exp(-2j * np.pi * m * _n / _N)
        _bin_cache[m] = p
    return p


def xcorr(code_i, code_k, lags_chips, m=0):
    """Normirana kompleksna cross-korelacija X_ik(τ) = (1/N)·Σ c_i[n]·c_k[n − τ]·e^{−j2πmn/N}
    lokalnog koda i i primljenog koda k pomaknutog za τ čipova (skalar ili niz;
    razlomljen pomak → linearna interpolacija između cijelih pomaka, točno za
    pravokutne čipove), u Doppler-binu m (frekvencijski pomak m·1 kHz).

    Za m = 0 i cijeli pomak vrijednosti su troznačne {−65, −1, 63}/1023 (Gold).
    Svi traženi pomaci računaju se jednim matričnim produktom.
    """
    lags = np.atleast_1d(np.asarray(lags_chips, float))
    l0 = np.floor(lags).astype(int)
    fr = lags - l0
    base = int(l0.min())
    span = int(l0.max()) - base + 2
    ints = base + np.arange(span)
    ref = code_i * _bin_phasor(int(m)) if m else code_i
    mat = code_k[(_n[None, :] - ints[:, None]) % _N]          # (span, N): c_k[n − l]
    vals = (mat @ ref) / _N
    j = l0 - base
    out = (1.0 - fr) * vals[j] + fr * vals[j + 1]
    return out if np.ndim(lags_chips) else out[0]


def _pair_phase(a, b):
    """Deterministička početna relativna faza nosioca para (FNV-1a hash → [0, 2π))."""
    h = 2166136261
    for ch in a + "|" + b:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return 2.0 * np.pi * (h / 2 ** 32)


class ChannelBank:
    """Svi vidljivi signali jednog banda u jednoj epohi (dijele antenu → interferiraju).

    Ulaz po signalu: id, PRN kod, udaljenost [m], Doppler [Hz], nominalni C/N0 [dB-Hz],
    opcionalno skupina (sustav) — MAI i cross-korelacija samo unutar skupine.
    `effective_cn0()` vraća C/N0 uz ometač + MAI (vektorski, O(N²) skalarno),
    `code_bias_m(i, ...)` DLL pristranost kanala i od multipatha + koherentne
    cross-korelacije (pravi Gold kodovi, samo za parove koji nisu zanemarivi).
    """

    def __init__(self, ids, codes, ranges_m, doppler_hz, cn0_db, t_coh=T_COH_S,
                 bl_hz=DLL_BL_HZ, d=DLL_SPACING_CHIPS, groups=None):
        self.ids = list(ids)
        self.codes = list(codes)
        self.ranges = np.asarray(ranges_m, float)
        self.dop = np.asarray(doppler_hz, float)
        self.cn0 = np.asarray(cn0_db, float)
        self.t_coh, self.bl, self.d = t_coh, bl_hz, d
        p = 10 ** (self.cn0 / 10.0)
        self.amp2 = p[None, :] / p[:, None]               # (C_k / C_i), [i, k]
        if groups is not None:
            # Interferiraju samo signali iste skupine (sustava): u stvarnosti su
            # sustavi razdvojeni frekvencijom (GLONASS FDMA, BeiDou B1I 1561 MHz)
            # ili modulacijom (Galileo BOC), iako simulator svima daje C/A-like kod.
            g = np.asarray(groups)
            self.amp2 = np.where(g[None, :] == g[:, None], self.amp2, 0.0)
        self.df = self.dop[None, :] - self.dop[:, None]   # Δf_ik = f_k − f_i
        # Koherentni težinski faktor para (vektorski, jednom po epohi): najbliža
        # spektralna linija m, ostatak (otkucaj) δ, w = √(C_k/C_i)·|sinc(πδT)|·|H(δ)|.
        self.m_bin = np.round(self.df / LINE_SPACING_HZ)
        self.beat = self.df - self.m_bin * LINE_SPACING_HZ
        self.w = np.sqrt(self.amp2) * coherent_gain(self.beat, t_coh) * loop_gain(self.beat, bl_hz)
        np.fill_diagonal(self.w, 0.0)

    def mai_n0_over_c(self):
        """Dodatni N0/C [s] po kanalu od cross-korelacije svih ostalih signala."""
        n = len(self.ids)
        if n < 2:
            return np.zeros(n)
        kap = mai_kappa(self.df, self.t_coh) * self.amp2
        np.fill_diagonal(kap, 0.0)
        return kap.sum(axis=1)

    def effective_cn0(self, jn_db=0.0):
        return effective_cn0_dbhz(self.cn0, jn_db, self.mai_n0_over_c())

    def code_bias_m(self, i, t, mp=None, mp_scale=1.0):
        """DLL pristranost koda kanala i [m]: multipath + koherentna cross-korelacija.

        Linearizirani nul-prijelaz koherentnog EML diskriminatora
        D(ε) = y(ε − d/2) − y(ε + d/2) (own: 2ε), y = Λ + α·Λ(· − δ) + Σ_k c_k·Re(X_k·e^{jφ}):
            ε = (2αδ − Σ_k c_k·ΔX_k) / (2·(1 + α)),  ΔX_k = X_k(lag+d/2) − X_k(lag−d/2)
        gdje je c_k = √(C_k/C_i)·sinc(π·δ_k·T)·|H_petlje(δ_k)| (δ_k = ostatak
        rel. Dopplera do najbliže linije), a faza nosioca rotira s Δf_ik·t.
        Vraća (bias_m, lost) — lost=True kad pristranost premaši linearno područje
        diskriminatora (|ε| > d/2: zabrava na cross-korelacijski vrh).
        """
        d = self.d
        alpha, delta_c = 0.0, 0.0
        if mp is not None:
            extra, att_raw = mp
            alpha = att_raw * mp_scale
            delta_c = extra / sp.METERS_PER_CHIP
        num = 2.0 * alpha * delta_c
        code_i = self.codes[i]
        code_len_m = sp.PRN_LENGTH * sp.METERS_PER_CHIP
        for k in np.nonzero(self.w[i] >= XCORR_MIN_WEIGHT)[0]:
            df = self.df[i, k]
            m = int(self.m_bin[i, k])
            # Kašnjenje koda k relativno na i [čip], unutar jednog kodnog perioda.
            lag = ((self.ranges[k] - self.ranges[i]) % code_len_m) / sp.METERS_PER_CHIP
            phase = 2.0 * np.pi * ((df * t) % 1.0) + _pair_phase(self.ids[i], self.ids[k])
            rot = np.exp(1j * phase)
            # Interferencija na položaju replike x je X_ik(lag − x): rani x = −d/2, kasni x = +d/2.
            xe, xl = xcorr(code_i, self.codes[k], (lag + d / 2.0, lag - d / 2.0), m)
            num -= self.w[i, k] * float(np.real((xe - xl) * rot))
        eps = num / (2.0 * (1.0 + alpha))
        lost = abs(eps) > d / 2.0
        return eps * sp.METERS_PER_CHIP, lost


def doppler_hz(sat_pos, sat_vel, rx_pos, rx_vel, freq):
    """Doppler [Hz] = −(d/dt range)/λ (ECEF)."""
    los = np.asarray(sat_pos, float) - np.asarray(rx_pos, float)
    u = los / np.linalg.norm(los, axis=-1, keepdims=True)
    rr = np.sum((np.asarray(sat_vel, float) - np.asarray(rx_vel, float)) * u, axis=-1)
    return -rr * freq / C


def survives_jamming(sat_pos, rx_pos, jn_db, power_offset_db=0.0):
    """Ostaje li satelit u zabravi (oba banda) uz ometač J/N [dB]? (bez MAI)

    Koristi ga i fazno praćenje (RTK), koje dijeli isti prag zabrave.
    """
    loss = jam_loss_db(jn_db)
    for band in BANDS:
        if float(cn0_dbhz(sat_pos, rx_pos, band, power_offset_db)[0]) - loss < TRACK_THRESHOLD_DBHZ:
            return False
    return True
