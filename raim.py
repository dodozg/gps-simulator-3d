"""RAIM (Receiver Autonomous Integrity Monitoring) — klasični snapshot RAIM s FDE.

Što radi, po epohi, iz pseudoudaljenosti i geometrije:

1. **Detekcija kvara (FD)** — težinski najmanji kvadrati daju rezidual r koji je
   ortogonalan na geometriju (pozicija + sat + ISB). Testna statistika
   T = rᵀ W r ima, kad nema kvara i kad je model šuma točan, chi-kvadrat
   razdiobu s dof = n − m stupnjeva slobode (n mjerenja, m nepoznanica). Prag T_d
   bira se tako da je vjerojatnost lažnog alarma P_FA.
2. **Isključivanje kvara (FDE)** — ako T > T_d i ima redundancije (dof ≥ 2),
   isključi satelit s najvećim normaliziranim rezidualom i ponovi.
3. **Zaštitne granice (HPL/VPL)** — "slope" metoda (Brown/RTCA): najveća
   horizontalna/vertikalna greška pozicije koju kvar na JEDNOM satelitu može
   izazvati, a da ga test još ne detektira s vjerojatnošću propusta P_MD.
   HPL = max_i Hslope_i · sqrt(λ), gdje je λ necentralni parametar za koji
   P(χ'²(dof, λ) < T_d) = P_MD.

Za razliku od starog praga (600 m apsolutno), ovo je STATISTIČKI test: osjetljivost
ovisi o šumu i geometriji, pa se i kvar od desetak metara detektira kad je
geometrija dobra, a sustav pošteno kaže kad integritet NIJE dostupan (HPL > HAL
ili nema redundancije).

Ograničenje koje ostaje (i to je lekcija): koordinirani spoof koji je
konzistentan sa SVIM mjerenjima ne ostavlja rezidual — RAIM ga ne vidi.

Bez scipy-ja: regularizirana nepotpuna gama funkcija (Numerical Recipes, serija +
kontinuirani razlomak) daje chi-kvadrat CDF; necentralni CDF je Poissonov zbroj.
"""
import math
from functools import lru_cache

import numpy as np

# --- Zadani parametri integriteta -------------------------------------------
RAIM_PFA = 1e-5      # vjerojatnost lažnog alarma po epohi
RAIM_PMD = 1e-3      # vjerojatnost propuštene detekcije
# Granice uzbune (alert limits). Klasični RAIM (samo GPS, bez SBAS-a) se koristi za
# ne-precizni prilaz (NPA, RNP 0.3): HAL = 0.3 NM = 556 m, bez vertikalnog zahtjeva.
# Strože faze (APV/LPV: HAL 40 m, VAL 50 m) traže augmentaciju — mogu se zadati.
RAIM_HAL = 556.0     # [m] horizontalna granica uzbune
RAIM_VAL = None      # [m] vertikalna granica uzbune (None = nema zahtjeva)


# --- Chi-kvadrat razdiobe (bez scipy) ---------------------------------------
def _gser(a, x):
    """Regularizirana donja nepotpuna gama P(a, x) — red (za x < a + 1)."""
    if x <= 0.0:
        return 0.0
    ap, s, d = a, 1.0 / a, 1.0 / a
    for _ in range(10_000):
        ap += 1.0
        d *= x / ap
        s += d
        if abs(d) < abs(s) * 1e-15:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a, x):
    """Regularizirana gornja nepotpuna gama Q(a, x) — kontinuirani razlomak (x ≥ a + 1)."""
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_cdf(x, k):
    """P(χ²_k ≤ x)."""
    if x <= 0.0:
        return 0.0
    a, xx = 0.5 * k, 0.5 * x
    return _gser(a, xx) if xx < a + 1.0 else 1.0 - _gcf(a, xx)


def chi2_sf(x, k):
    """P(χ²_k > x) — precizno i za vrlo male repove (bez 1 − 1e-9 poništavanja)."""
    if x <= 0.0:
        return 1.0
    a, xx = 0.5 * k, 0.5 * x
    return 1.0 - _gser(a, xx) if xx < a + 1.0 else _gcf(a, xx)


def _bisect(f, lo, hi, iters=200):
    """Korijen monotone f na [lo, hi] (f(lo) i f(hi) suprotnih predznaka)."""
    flo = f(lo)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
        if hi - lo < 1e-10 * max(1.0, hi):
            break
    return 0.5 * (lo + hi)


@lru_cache(maxsize=None)
def chi2_isf(p, k):
    """Prag x za koji je P(χ²_k > x) = p (inverz repa)."""
    hi = max(10.0, 2.0 * k)
    while chi2_sf(hi, k) > p:
        hi *= 2.0
    # u log-domeni je funkcija glađa (repovi padaju eksponencijalno)
    return _bisect(lambda x: math.log(chi2_sf(x, k)) - math.log(p), 0.0, hi)


def ncx2_cdf(x, k, lam):
    """P(χ'²(k, λ) ≤ x) — Poissonov zbroj centralnih chi-kvadrat CDF-ova."""
    if lam <= 0.0:
        return chi2_cdf(x, k)
    half = 0.5 * lam
    # Poissonove težine izvan mode ± 12σ su zanemarive (< 1e-30)
    lo = max(0, int(half - 12.0 * math.sqrt(half) - 5))
    hi = int(half + 12.0 * math.sqrt(half) + 20)
    log_half = math.log(half)
    total = 0.0
    for j in range(lo, hi + 1):
        w = math.exp(-half + j * log_half - math.lgamma(j + 1))
        total += w * chi2_cdf(x, k + 2 * j)
    return min(max(total, 0.0), 1.0)


@lru_cache(maxsize=None)
def noncentrality(k, pfa=RAIM_PFA, pmd=RAIM_PMD):
    """λ za koji test s pragom T_d(k, P_FA) propušta kvar s vjerojatnošću P_MD."""
    td = chi2_isf(pfa, k)
    hi = 10.0
    while ncx2_cdf(td, k, hi) > pmd:
        hi *= 2.0
    return _bisect(lambda lam: ncx2_cdf(td, k, lam) - pmd, 0.0, hi)


# --- RAIM -------------------------------------------------------------------
def _enu_rotation(pos):
    """3×3 matrica ECEF → ENU (redci: istok, sjever, gore) u točki pos."""
    x, y, z = pos
    lon = math.atan2(y, x)
    lat = math.atan2(z, math.hypot(x, y))
    sl, cl = math.sin(lon), math.cos(lon)
    sp, cp = math.sin(lat), math.cos(lat)
    return np.array([[-sl, cl, 0.0],
                     [-sp * cl, -sp * sl, cp],
                     [cp * cl, cp * sl, sp]])


def _solve(G, y, sigma):
    """WLS: vrati (K, S, r, T) — K = (GᵀWG)⁻¹GᵀW, S = I − GK, r = Sy, T = rᵀWr."""
    w = 1.0 / sigma**2
    GW = G.T * w
    try:
        N_inv = np.linalg.inv(GW @ G)
    except np.linalg.LinAlgError:
        return None
    K = N_inv @ GW
    S = np.eye(len(y)) - G @ K
    r = S @ y
    T = float(np.sum(w * r * r))
    return K, S, r, T


def _protection_levels(K, S, sigma, enu, lam):
    """HPL/VPL slope metodom (najgori pojedinačni satelit)."""
    Kenu = enu @ K[0:3, :]
    sii = np.clip(np.diag(S), 0.0, None)
    hslope = np.zeros(len(sigma))
    vslope = np.zeros(len(sigma))
    ok = sii > 1e-9            # mjerenje bez redundancije (npr. jedini sat sustava) se ne nadzire
    hslope[ok] = np.hypot(Kenu[0, ok], Kenu[1, ok]) * sigma[ok] / np.sqrt(sii[ok])
    vslope[ok] = np.abs(Kenu[2, ok]) * sigma[ok] / np.sqrt(sii[ok])
    sq = math.sqrt(lam)
    return float(hslope.max() * sq), float(vslope.max() * sq)


def run_raim(G, y, sigma, pos, ids=None, pfa=RAIM_PFA, pmd=RAIM_PMD,
             hal=RAIM_HAL, val=RAIM_VAL, exclude=True):
    """Snapshot RAIM s FDE.

    G:     n×m matrica geometrije (prva 3 stupca = ECEF pozicija, ostali sat/ISB).
    y:     n inovacija/reziduala pseudoudaljenosti [m] oko točke linearizacije.
    sigma: n devijacija mjerenja [m].
    pos:   ECEF točka linearizacije (za ENU rotaciju).
    ids:   oznake mjerenja (za poruke); exclude=False -> samo detekcija.

    Vraća dict: status ('ok' | 'excluded' | 'alarm' | 'unavailable'),
    excluded (indeksi), test (T), threshold (T_d), dof, hpl, vpl, hal, val,
    available (HPL≤HAL i VPL≤VAL), normalized (normalizirani reziduali).
    """
    G = np.asarray(G, float)
    y = np.asarray(y, float)
    sigma = np.asarray(sigma, float)
    n_all, m = G.shape
    active = np.arange(n_all)
    excluded = []
    enu = _enu_rotation(pos)
    out = {"status": "unavailable", "excluded": excluded, "test": None,
           "threshold": None, "dof": 0, "hpl": None, "vpl": None,
           "hal": hal, "val": val, "available": False, "normalized": None}

    while True:
        dof = len(active) - m
        if dof < 1:
            # nema redundancije: kvar se ne može ni detektirati
            out["dof"] = max(dof, 0)
            return out
        sol = _solve(G[active], y[active], sigma[active])
        if sol is None:
            return out
        K, S, r, T = sol
        td = chi2_isf(pfa, dof)
        sii = np.clip(np.diag(S), 1e-12, None)
        wnorm = np.abs(r) / (sigma[active] * np.sqrt(sii))
        out.update(test=T, threshold=td, dof=dof)
        if T <= td:
            hpl, vpl = _protection_levels(K, S, sigma[active], enu, noncentrality(dof, pfa, pmd))
            out.update(status="excluded" if excluded else "ok", hpl=hpl, vpl=vpl,
                       available=bool(hpl <= hal and (val is None or vpl <= val)))
            norm_all = np.full(n_all, np.nan)
            norm_all[active] = wnorm
            out["normalized"] = norm_all
            return out
        if not exclude or dof < 2:
            out["status"] = "alarm"          # kvar detektiran, ali se ne može izolirati
            norm_all = np.full(n_all, np.nan)
            norm_all[active] = wnorm
            out["normalized"] = norm_all
            return out
        k = int(np.argmax(wnorm))
        excluded.append(int(active[k]))
        active = np.delete(active, k)
