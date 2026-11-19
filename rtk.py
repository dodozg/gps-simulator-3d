"""Carrier-phase RTK (Real-Time Kinematic) — cm-precizno relativno pozicioniranje.

Za razliku od kodnog rješenja (pseudoudaljenost, ~desetci metara zbog multipatha),
RTK koristi FAZU nosioca (valna duljina L1 ~19 cm, šum ~mm) i dvostruke razlike
(double differencing, DD) između rovera/baze i para satelita, čime se ponište
satni pomaci i (kod kratke baze) atmosfera. Ostaje cjelobrojna neodređenost
(integer ambiguity) koju treba razriješiti; kad se fiksira na ispravan cijeli broj,
rješenje je centimetarsko.

Ovdje je implementiran statički jedno-bazni RTK:
  1. prikupi DD faze kroz više epoha (geometrija se mijenja kako sateliti putuju),
  2. float rješenje (LS): baseline + realne DD neodređenosti,
  3. fiksiranje cijelih brojeva zaokruživanjem (u simulaciji sa mm šumom pouzdano),
  4. fiksno rješenje: baseline uz fiksne cijele brojeve -> cm.

Primjer:
    python rtk.py
"""
import argparse
import numpy as np

from satellite import WalkerDeltaConstellation
from utils import lla_to_ecef
from physics_engine import C

F_L1 = 1575.42e6
LAMBDA1 = C / F_L1          # ~0.1903 m, valna duljina L1
PHASE_SIGMA_M = 0.002       # šum faze nosioca ~2 mm
CODE_SIGMA_M = 3.0          # šum koda ~3 m (za usporedbu)


def _visible(sat_positions, rec_pos, mask_deg):
    up = rec_pos / np.linalg.norm(rec_pos)
    vis = set()
    for sid, sp in sat_positions.items():
        v = sp - rec_pos
        el = np.degrees(np.arcsin(np.dot(up, v / np.linalg.norm(v))))
        if el >= mask_deg:
            vis.add(sid)
    return vis


def dd_design(sat_pos, x, ref, others):
    """Geometrija dvostruke razlike za prijemnik na poziciji `x` (ECEF).

    Vrati (dd_rho, rows): dd_rho[k] = rho(others[k]) - rho(ref) [m] i retke
    Jacobiana d(dd_rho)/dx = -(e_s - e_ref), gdje je e jedinični vektor prema
    satelitu. Zajednički dio offline (`rtk_solve`) i živog (`RTKFilter`) RTK-a.
    """
    v_ref = sat_pos[ref] - x
    rho_ref = np.sqrt(v_ref @ v_ref)
    e_ref = v_ref / rho_ref
    v = np.array([sat_pos[s] for s in others], dtype=float) - x
    rho = np.sqrt(np.einsum("ij,ij->i", v, v))
    return rho - rho_ref, -(v / rho[:, None] - e_ref)


def rtk_solve(rover_llh, base_llh, n_epochs=40, dt_epoch=30.0, seed=0, mask_deg=15.0):
    """Riješi položaj rovera RTK-om uz poznatu bazu. Vrati metrike ili None."""
    rng = np.random.default_rng(seed)
    con = WalkerDeltaConstellation(rng=rng)
    R = np.array(lla_to_ecef(*rover_llh), dtype=float)   # prava pozicija rovera
    B = np.array(lla_to_ecef(*base_llh), dtype=float)     # baza (poznata točno)

    times = [i * dt_epoch for i in range(n_epochs)]
    sat_pos = {}
    for t in times:
        con.update_all(t)
        sat_pos[t] = {s.sat_id: s.current_pos.copy() for s in con.satellites}

    # Sateliti vidljivi iz OBA prijemnika u SVIM epohama (bez cycle-slipa).
    common = None
    for t in times:
        vis = _visible(sat_pos[t], R, mask_deg) & _visible(sat_pos[t], B, mask_deg)
        common = vis if common is None else (common & vis)
    common = sorted(common)
    if len(common) < 5:
        return None
    ref = common[0]
    others = common[1:]
    m = len(others)

    # Fiksne cjelobrojne neodređenosti po (prijemnik, sat) — konstantne kroz epohe.
    Nr = {s: int(rng.integers(-200, 200)) for s in common}
    Nb = {s: int(rng.integers(-200, 200)) for s in common}
    Ndd_true = np.array([(Nr[s] - Nb[s]) - (Nr[ref] - Nb[ref]) for s in others])

    # Mjerenja faze (u metrima) generirana JEDNOM (fiksni šum), i DD opažanja.
    DDL = {}          # t -> vektor DD faze [m] po 'others'
    DD_range_b = {}   # t -> vektor DD geometrijske udaljenosti baze [m]
    for t in times:
        sp = sat_pos[t]
        Lr = {s: np.linalg.norm(sp[s] - R) + LAMBDA1 * Nr[s] + rng.normal(0, PHASE_SIGMA_M) for s in common}
        Lb = {s: np.linalg.norm(sp[s] - B) + LAMBDA1 * Nb[s] + rng.normal(0, PHASE_SIGMA_M) for s in common}
        rb = {s: np.linalg.norm(sp[s] - B) for s in common}
        DDL[t] = np.array([(Lr[s] - Lb[s]) - (Lr[ref] - Lb[ref]) for s in others])
        DD_range_b[t] = np.array([(rb[s] - rb[ref]) for s in others])

    def _build(x, fixed_int=None):
        """Sagradi LS sustav A u = b. fixed_int=None -> float (dx+Ndd), inace samo dx."""
        rowsA, rowsb = [], []
        for t in times:
            dd_rho, dd_rows = dd_design(sat_pos[t], x, ref, others)
            for k, s in enumerate(others):
                Cc = dd_rho[k] - DD_range_b[t][k]
                coef_dx = dd_rows[k]
                if fixed_int is None:
                    row = np.zeros(3 + m)
                    row[:3] = coef_dx
                    row[3 + k] = LAMBDA1
                    rowsA.append(row)
                    rowsb.append(DDL[t][k] - Cc)
                else:
                    rowsA.append(coef_dx)
                    rowsb.append(DDL[t][k] - Cc - LAMBDA1 * fixed_int[k])
        return np.array(rowsA), np.array(rowsb)

    # --- FLOAT: zajednički Gauss-Newton za baseline + realne neodređenosti ---
    x = B.copy()
    Ndd_float = np.zeros(m)
    for _ in range(10):
        A, b = _build(x, fixed_int=None)
        u, *_ = np.linalg.lstsq(A, b, rcond=None)
        dx, Ndd_float = u[:3], u[3:]
        x = x + dx
        if np.linalg.norm(dx) < 1e-4:
            break
    x_float = x.copy()

    # --- FIKSIRANJE: zaokruži na cijele brojeve ---
    Ndd_fixed = np.round(Ndd_float).astype(int)

    # --- FIXED: Gauss-Newton za baseline uz fiksne cijele brojeve ---
    x = B.copy()
    for _ in range(10):
        A, b = _build(x, fixed_int=Ndd_fixed)
        dx, *_ = np.linalg.lstsq(A, b, rcond=None)
        x = x + dx
        if np.linalg.norm(dx) < 1e-5:
            break
    x_fixed = x.copy()

    return dict(
        baseline_m=float(np.linalg.norm(R - B)),
        n_common=len(common), n_epochs=n_epochs,
        float_err_m=float(np.linalg.norm(x_float - R)),
        fixed_err_m=float(np.linalg.norm(x_fixed - R)),
        ar_success=bool(np.array_equal(Ndd_fixed, Ndd_true)),
    )


# =============================================================================
# ŽIVI (per-epoha) RTK — za web simulaciju (SimSession)
# =============================================================================
# Offline `rtk_solve` skupi sve epohe pa riješi jednim LS-om. U živoj simulaciji
# epohe stižu jedna po jedna (10 Hz), rover se može gibati (kinematika) i sateliti
# izlaze/ulaze, pa je ovdje isti model DD faze složen REKURZIVNO (Kalmanov filtar):
#
#   stanje  x = [položaj rovera (3) | SD neodređenosti N_s po satelitu (ciklusi)]
#   mjerenja po epohi: DD koda (m) + DD faze (m) unutar svakog sustava
#
# SD (rover−baza) neodređenost po satelitu umjesto DD-a: referentni satelit se
# smije mijenjati iz epohe u epohu, a novi/izgubljeni satelit samo doda/makne
# jedan element stanja. Cjelobrojne su tek DD kombinacije (N_s − N_ref), pa se
# fiksiranje radi nad njima (transformacija D).
#
# Fiksiranje: DD float neodređenosti dovoljno male nesigurnosti (σ < FIX_SIGMA_CYC)
# zaokruže se na cijele brojeve i provjere ratio testom (najbliži susjedni cijeli
# vektor mora biti ≥ RATIO_MIN puta "dalje" u metrici kovarijance). Prihvaćeni
# cijeli brojevi se "drže" (fix-and-hold: pseudo-mjerenje vrlo male varijance), pa
# FIX preživi i kretanje rovera i promjenu referentnog satelita.
#
# Kinematika: položaj nema dinamički model (rover u simulaciji "skače" i do ~3 km
# po epohi i prati teren), pa se položaj u svakoj epohi ponovno inicijalizira iz
# DD koda (bijeli šum), a informaciju između epoha nose SAMO neodređenosti — kao
# "kinematic" način u RTKLIB-u. Statički rover zadržava položaj u stanju.

LIVE_MASK_DEG = 10.0         # elevacijska maska za RTK (rover I baza)
LIVE_CODE_SIGMA_M = 0.3      # šum koda u zenitu (po prijemniku) — nakon glađenja
LIVE_PHASE_SIGMA_M = PHASE_SIGMA_M
ATMO_PPM = 1.0               # rezidualna diferencijalna ionosfera ~1 mm/km (1 ppm)
RTK_SYSTEMS = ("GPS", "GAL", "BDS")   # GLONASS (FDMA, razl. valne duljine) izostavljen
VAR_POS_KIN = 1e4            # [m²] a-priori varijanca položaja kad se reinicijalizira
VAR_POS_STATIC_Q = 1e-8      # [m²/epoha] procesni šum statičkog položaja
VAR_N0 = 100.0               # [ciklus²] a-priori varijanca nove SD neodređenosti
AR_MAX_SIGMA_CYC = 1.5      # DD neodređenost ulazi u LAMBDA ako je σ < ovo [ciklus]
AR_MAX_LAMBDA = 3            # partial AR: najviše punih LAMBDA pretraga po epohi (CPU)
RATIO_MIN = 3.0              # ratio test (drugi najbolji / najbolji kandidat)
P_BOOT_MIN = 0.999           # tražena vjerojatnost uspjeha (bootstrapping, nakon Z)
MIN_FIX_DD = 4               # najmanje fiksiranih DD-a za FIX (3 položaj + 1 višak)
HOLD_VAR = 1e-4              # [ciklus²] varijanca "hold" pseudo-mjerenja (+ atmosfera)
FIX_RMS_MAX_M = 0.03         # validacija: RMS DD faznih reziduala uz fiks
MAX_BAD_FIX = 3              # toliko uzastopnih loših validacija -> reset neodređenosti


def _el_sigma(sigma0, el_rad):
    """Elevacijski ovisan šum: σ0 / sin(el) (niski sateliti su bučniji)."""
    return sigma0 / max(np.sin(el_rad), 0.1)


def _atmo_sigma(baseline_m, el_rad):
    """Očekivana (1σ) rezidualna diferencijalna atmosfera po satelitu [m].

    Ista ppm-skala kao u `CarrierPhaseSim`; filtar ne zna stvarni pomak, ali zna
    njegovu veličinu (∝ duljini baze), pa ga uključi u varijancu mjerenja i u
    prag fiksiranja. Zato duga baza prirodno sprječava (krivi) FIX."""
    return ATMO_PPM * 1e-6 * baseline_m / max(np.sin(el_rad), 0.1)


def _elev_vec(rec, sats):
    """Elevacije [rad] niza satelita (n×3) gledano s prijemnika `rec`."""
    v = sats - rec
    up = rec / np.linalg.norm(rec)
    return np.arcsin((v @ up) / np.linalg.norm(v, axis=1))


# --- LAMBDA: dekorelacija + cjelobrojna pretraga (ILS) ------------------------
# DD float neodređenosti su jako korelirane (pojedinačne σ velike, a "prava"
# nesigurnost leži u uskom, ukošenom elipsoidu). LAMBDA (Teunissen 1995) ih
# cjelobrojnom Z-transformacijom dekorelira i u tom prostoru traži najbliža
# cijela rješenja (MLAMBDA, Chang et al. 2005). Port algoritma iz RTKLIB lambda.c.

def _lambda_ld(Q):
    """Q = Lᵀ·diag(d)·L, L donja trokutasta s jedinicama na dijagonali."""
    n = len(Q)
    A = np.array(Q, dtype=float)
    L = np.zeros((n, n))
    d = np.zeros(n)
    for i in range(n - 1, -1, -1):
        d[i] = A[i, i]
        if d[i] <= 0.0:
            raise np.linalg.LinAlgError("Q nije pozitivno definitna")
        a = np.sqrt(d[i])
        L[i, :i + 1] = A[i, :i + 1] / a
        A[:i, :i] -= np.outer(L[i, :i], L[i, :i])
        L[i, :i + 1] /= L[i, i]
    return L, d


def _lambda_reduction(L, d):
    """Cjelobrojna Gaussova transformacija + permutacije (dekorelacija).

    Vrati (Z, L, d) nakon redukcije. Namjerno čisti Python nad listama: za male
    matrice (n ≤ ~25) je ~4× brži od numpy rezanja (stotine sitnih operacija)."""
    from math import floor
    n = len(d)
    L = [list(map(float, r)) for r in L]
    d = [float(v) for v in d]
    Z = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    j = k = n - 2
    while j >= 0:
        if j <= k:
            for i in range(j + 1, n):            # gauss(i, j)
                mu = floor(L[i][j] + 0.5)
                if mu:
                    for r in range(i, n):
                        L[r][j] -= mu * L[r][i]
                    for r in range(n):
                        Z[r][j] -= mu * Z[r][i]
        lj = L[j + 1][j]
        delta = d[j] + lj * lj * d[j + 1]
        if delta + 1e-6 < d[j + 1]:              # perm(j)
            eta = d[j] / delta
            lam = d[j + 1] * lj / delta
            d[j] = eta * d[j + 1]
            d[j + 1] = delta
            row0, row1 = L[j], L[j + 1]
            for c in range(j):
                a0, a1 = row0[c], row1[c]
                row0[c] = -lj * a0 + a1
                row1[c] = eta * a0 + lam * a1
            row1[j] = lam
            for r in range(j + 2, n):
                rr = L[r]
                rr[j], rr[j + 1] = rr[j + 1], rr[j]
            for r in range(n):
                rr = Z[r]
                rr[j], rr[j + 1] = rr[j + 1], rr[j]
            k = j
            j = n - 2
        else:
            j -= 1
    return np.array(Z), np.array(L), np.array(d)


def _lambda_search(L, d, zs, m=2, loopmax=10000):
    """MLAMBDA pretraga: m najboljih cijelih vektora i njihove kvadratne norme."""
    n = len(d)
    S = np.zeros((n, n))
    dist = np.zeros(n)
    zb = np.zeros(n)
    z = np.zeros(n)
    step = np.zeros(n)
    sgn = lambda x: -1.0 if x <= 0.0 else 1.0
    cands, norms = [], []
    maxdist = np.inf
    k = n - 1
    zb[k] = zs[k]
    z[k] = np.floor(zb[k] + 0.5)
    y = zb[k] - z[k]
    step[k] = sgn(y)
    for _ in range(loopmax):
        newdist = dist[k] + y * y / d[k]
        if newdist < maxdist:
            if k != 0:
                k -= 1
                dist[k] = newdist
                S[k, :k + 1] = S[k + 1, :k + 1] + (z[k + 1] - zb[k + 1]) * L[k + 1, :k + 1]
                zb[k] = zs[k] + S[k, k]
                z[k] = np.floor(zb[k] + 0.5)
                y = zb[k] - z[k]
                step[k] = sgn(y)
            else:
                if len(cands) < m:
                    cands.append(z.copy())
                    norms.append(newdist)
                else:
                    imax = int(np.argmax(norms))
                    if newdist < norms[imax]:
                        cands[imax] = z.copy()
                        norms[imax] = newdist
                if len(cands) == m:
                    maxdist = max(norms)
                z[0] += step[0]
                y = zb[0] - z[0]
                step[0] = -step[0] - sgn(step[0])
        else:
            if k == n - 1:
                break
            k += 1
            z[k] += step[k]
            y = zb[k] - z[k]
            step[k] = -step[k] - sgn(step[k])
    order = np.argsort(norms)
    return [cands[i] for i in order], [norms[i] for i in order]


def lambda_ils(a, Q, m=2):
    """Cjelobrojni LS (LAMBDA) za float vektor `a` s kovarijancom `Q`.

    Vrati (kandidati, norme, p_boot): kandidati u ORIGINALNOM prostoru (cijeli
    brojevi), uzlazno po normi (a−z)ᵀQ⁻¹(a−z), te vjerojatnost uspjeha
    bootstrappinga u dekoreliranom prostoru (donja granica za ILS)."""
    from math import erf, sqrt
    L, d = _lambda_ld(Q)
    Z, L, d = _lambda_reduction(L, d)
    zs = Z.T @ a
    cz, norms = _lambda_search(L, d, zs, m=m)
    Zinv_t = np.linalg.inv(Z.T)
    cands = [np.round(Zinv_t @ c) for c in cz]
    p_boot = 1.0
    for di in d:
        p_boot *= erf(1.0 / (2.0 * sqrt(2.0 * di)))     # 2Φ(1/(2σ)) − 1
    return cands, norms, p_boot


def _ils_fast_or_lambda(a, Q, sig, budget=None):
    """Brzi put za živi RTK (poziva se svaku epohu).

    - Male σ (tipično nakon "hold"): ako Boolova donja granica uspjeha samog
      zaokruživanja, 1 − Σ P(|e_i| > 0.5), već doseže P_BOOT_MIN, zaokruživanje
      je (s tom vjerojatnošću) ILS rješenje; drugi kandidat = najbliži susjed po
      jednoj komponenti (za ratio).
    - Inače ADOP (det Q)^(1/2n) — invarijantan na Z-transformaciju i daje GORNJU
      granicu uspjeha ILS-a. Ako ni ona ne doseže P_BOOT_MIN, LAMBDA se preskače
      (vrati None) — ista odluka, a bez skupe dekorelacije dok je rješenje float.
    - Inače puni LAMBDA (ako `budget` = [preostalo] dopušta; inače None)."""
    from math import erf, erfc, sqrt
    n = len(a)
    p_round = 1.0 - sum(erfc(0.5 / (sqrt(2.0) * si)) for si in sig) if np.max(sig) < 0.2 else 0.0
    if p_round >= P_BOOT_MIN:
        z = np.round(a)
        r = a - z
        Qi = np.linalg.inv(Q)
        q1 = float(r @ Qi @ r)
        q2 = np.inf
        Qr = Qi @ r
        for i in range(n):                   # (r - s e_i)ᵀQ⁻¹(r - s e_i)
            st = np.sign(r[i]) if r[i] != 0 else 1.0
            q2 = min(q2, q1 - 2.0 * st * Qr[i] + Qi[i, i])
        return [z, None], [q1, q2], p_round
    sign, logdet = np.linalg.slogdet(Q)
    if sign <= 0:
        raise np.linalg.LinAlgError("Q nije pozitivno definitna")
    adop = float(np.exp(logdet / (2.0 * n)))
    if erf(1.0 / (2.0 * sqrt(2.0) * adop)) ** n < P_BOOT_MIN:
        return None, None, None
    if budget is not None:
        if budget[0] <= 0:
            return None, None, None
        budget[0] -= 1
    return lambda_ils(a, Q, m=2)


class CarrierPhaseSim:
    """Generator sirovih mjerenja koda i faze za rover i bazu (simulirana istina).

    Mjerenja se rade iz PRAVIH pozicija satelita (`current_pos`); estimator dobiva
    OBJAVLJENE (`broadcast_pos`, s efemeridnom greškom) — kao pravi prijemnik.
    Satni pomaci prijemnika i satelita su prisutni i ponište se u DD-u. Po satelitu
    se drži "lock": cjelobrojne neodređenosti rovera i baze + faktor rezidualne
    atmosfere. Kad satelit ispadne iz praćenja (ispod maske, ugašen, ometan), lock
    se gubi i pri ponovnom pojavljivanju dobiva NOVE cijele brojeve (kao cycle slip).
    """

    def __init__(self, rng):
        self.rng = rng
        self.locks = {}

    def reset(self):
        self.locks = {}

    def observe(self, sats, rover, base, baseline_m):
        """sats: lista (sat_id, system, true_pos, el_rover_rad, sat_clock_m).

        Vrati dict sat_id -> {P_r, P_b, L_r, L_b} [m] (L = faza u metrima)."""
        rng = self.rng
        clk_r = rng.normal(0.0, 1e3)        # satni pomak rovera [m] (poništi se u DD)
        clk_b = rng.normal(0.0, 1e3)        # satni pomak baze [m]
        present = set()
        out = {}
        for sid, _sys, sp, el, sat_clk in sats:
            present.add(sid)
            lk = self.locks.get(sid)
            if lk is None:
                lk = self.locks[sid] = (int(rng.integers(-200, 200)),
                                        int(rng.integers(-200, 200)),
                                        float(rng.normal(0.0, 1.0)))
            n_r, n_b, k_atm = lk
            rho_r = np.linalg.norm(sp - rover)
            rho_b = np.linalg.norm(sp - base)
            # Rezidualna (diferencijalna) ionosfera raste s duljinom baze: kod kasni,
            # faza "žuri" (iono-like). Za par km ~mm, za desetke km -> ometa fiks.
            d_atm = k_atm * _atmo_sigma(baseline_m, el)
            sc = _el_sigma(LIVE_CODE_SIGMA_M, el)
            sl = _el_sigma(LIVE_PHASE_SIGMA_M, el)
            out[sid] = dict(
                P_r=rho_r + clk_r - sat_clk + d_atm + rng.normal(0.0, sc),
                P_b=rho_b + clk_b - sat_clk + rng.normal(0.0, sc),
                L_r=rho_r + clk_r - sat_clk - d_atm + LAMBDA1 * n_r + rng.normal(0.0, sl),
                L_b=rho_b + clk_b - sat_clk + LAMBDA1 * n_b + rng.normal(0.0, sl),
            )
        for sid in list(self.locks):
            if sid not in present:
                del self.locks[sid]          # izgubljen lock -> nove neodređenosti
        return out

    def true_sd_int(self, sid):
        """Prava SD neodređenost (N_r − N_b) — samo za testove/dijagnostiku."""
        lk = self.locks.get(sid)
        return None if lk is None else lk[0] - lk[1]


class RTKFilter:
    """Rekurzivni RTK estimator (float -> fix-and-hold). Vidi blok-komentar gore."""

    def __init__(self, base_ecef):
        self.base = np.asarray(base_ecef, dtype=float)
        self.reset()

    def reset(self):
        self.ids = []                        # redoslijed SD neodređenosti u stanju
        self.x = None                        # [pos(3), N...]
        self.P = None
        self.held = {}                       # sat_id -> True ako je u "hold" skupu
        self.status = "none"                 # none | float | fixed
        self.pos = None                      # trenutno rješenje (fix ako postoji, inače float)
        self.pos_float = None
        self.n_dd = 0
        self.n_fixed = 0
        self.ratio = None
        self.p_boot = None
        self.bad_fix = 0
        self.fixed_pairs = []                # (ref, sat, DD cijeli broj) zadnjeg fiksa

    # --- održavanje stanja ------------------------------------------------
    def _sync_states(self, obs):
        """Makni neodređenosti satelita kojih više nema, dodaj nove."""
        keep = [i for i, s in enumerate(self.ids) if s in obs]
        idx = [0, 1, 2] + [3 + i for i in keep]
        self.x = self.x[idx]
        self.P = self.P[np.ix_(idx, idx)]
        self.ids = [self.ids[i] for i in keep]
        for s in list(self.held):
            if s not in obs:
                del self.held[s]
        new = [s for s in obs if s not in self.ids]
        if new:
            n0 = len(self.x)
            n1 = n0 + len(new)
            x = np.zeros(n1)
            x[:n0] = self.x
            P = np.zeros((n1, n1))
            P[:n0, :n0] = self.P
            for k, s in enumerate(new):
                o = obs[s]
                # inicijalna SD neodređenost iz faze − kod (satovi se ponište)
                x[n0 + k] = ((o["L_r"] - o["L_b"]) - (o["P_r"] - o["P_b"])) / LAMBDA1
                P[n0 + k, n0 + k] = VAR_N0
            self.x, self.P = x, P
            self.ids += new

    def _dd_index(self, obs, el):
        """DD parovi po sustavu: (ref_idx, sat_idx) u self.ids; ref = najviši satelit."""
        by_sys = {}
        for i, s in enumerate(self.ids):
            by_sys.setdefault(obs[s]["system"], []).append(i)
        ref_idx, sat_idx = [], []
        for sy in sorted(by_sys):
            ii = by_sys[sy]
            if len(ii) < 2:
                continue
            r = max(ii, key=lambda i: el[self.ids[i]])
            for i in ii:
                if i != r:
                    ref_idx.append(r)
                    sat_idx.append(i)
        return np.array(ref_idx, dtype=int), np.array(sat_idx, dtype=int)

    def _dd_geometry(self, x, S, rb, ri, si):
        """DD geometrija (rover−baza) za poziciju x: (geo [m], Jacobian n_dd×3)."""
        v = S - x
        rho = np.sqrt(np.einsum("ij,ij->i", v, v))
        e = v / rho[:, None]
        geo = (rho[si] - rho[ri]) - (rb[si] - rb[ri])
        return geo, -(e[si] - e[ri])

    def _code_position(self, x0, S, rb, ddP, ri, si):
        """DD-kodni LS položaj (Gauss-Newton) — linearizacijska točka/a-priori."""
        x = np.array(x0, dtype=float)
        for _ in range(8):
            geo, G = self._dd_geometry(x, S, rb, ri, si)
            dx, *_ = np.linalg.lstsq(G, ddP - geo, rcond=None)
            x = x + dx
            if dx @ dx < 1e-6:
                break
        return x

    @staticmethod
    def _dd_cov(var_sd, ri, si):
        """Kovarijanca DD-a: var(s) + var(ref), korelirani preko zajedničkog ref-a."""
        same = ri[:, None] == ri[None, :]
        return np.where(same, var_sd[ri][:, None], 0.0) + np.diag(var_sd[si])

    # --- jedna epoha ------------------------------------------------------
    def step(self, obs, sat_pos, el, kinematic):
        """obs: sat_id -> {system, P_r, P_b, L_r, L_b}; sat_pos: objavljene pozicije;
        el: sat_id -> elevacija na roveru [rad]. Vrati status ('none'/'float'/'fixed')."""
        if self.x is None:
            self.x = np.zeros(3)
            self.P = np.eye(3) * VAR_POS_KIN
            self.ids = []
        self._sync_states(obs)
        ri, si = self._dd_index(obs, el)
        n_dd = len(si)
        self.n_dd = n_dd
        if n_dd < 4:
            self.status, self.pos, self.pos_float = "none", None, None
            self.n_fixed, self.ratio, self.p_boot = 0, None, None
            return self.status

        ids = self.ids
        S = np.array([sat_pos[s] for s in ids], dtype=float)
        rb = np.linalg.norm(S - self.base, axis=1)
        P_sd = np.array([obs[s]["P_r"] - obs[s]["P_b"] for s in ids])
        L_sd = np.array([obs[s]["L_r"] - obs[s]["L_b"] for s in ids])
        elv = np.array([el[s] for s in ids])
        ddP = P_sd[si] - P_sd[ri]
        ddL = L_sd[si] - L_sd[ri]

        # --- predikcija položaja ---
        first = not np.any(self.x[:3])
        if kinematic or first:
            x0 = self.pos if self.pos is not None else (self.base if first else self.x[:3])
            self.x[:3] = self._code_position(x0, S, rb, ddP, ri, si)
            self.P[:3, :] = 0.0
            self.P[:, :3] = 0.0
            self.P[:3, :3] = np.eye(3) * VAR_POS_KIN
        else:
            self.P[:3, :3] += np.eye(3) * VAR_POS_STATIC_Q

        # --- mjerni model: DD kod + DD faza ---
        n = len(self.x)
        rows = np.arange(n_dd)
        D = np.zeros((n_dd, n))               # DD transformacija nad stanjem (N_s − N_ref)
        D[rows, 3 + si] = 1.0
        D[rows, 3 + ri] = -1.0
        geo, G = self._dd_geometry(self.x[:3], S, rb, ri, si)
        H = np.zeros((2 * n_dd, n))
        H[:n_dd, :3] = G
        H[n_dd:, :3] = G
        H[n_dd:, 3:] = LAMBDA1 * D[:, 3:]
        y = np.concatenate([ddP - geo, ddL - geo - LAMBDA1 * (D @ self.x)])
        sin_el = np.maximum(np.sin(elv), 0.1)
        var_c = 2.0 * (LIVE_CODE_SIGMA_M / sin_el) ** 2       # SD varijanca koda
        var_l = 2.0 * (LIVE_PHASE_SIGMA_M / sin_el) ** 2      # SD varijanca faze
        R = np.zeros((2 * n_dd, 2 * n_dd))
        R[:n_dd, :n_dd] = self._dd_cov(var_c, ri, si)
        R[n_dd:, n_dd:] = self._dd_cov(var_l, ri, si)
        # Rezidualna atmosfera NIJE u R: to je (sporo promjenjiv) POMAK, ne bijeli
        # šum — filtar ga ne bi "uprosječio". Umjesto toga ulazi kao donja granica
        # nesigurnosti pri fiksiranju (b2), u varijancu "hold"-a i u validaciju.
        bl = float(np.linalg.norm(self.x[:3] - self.base))
        atm = (ATMO_PPM * 1e-6 * bl / sin_el) ** 2
        b2 = (atm[si] + atm[ri]) / LAMBDA1 ** 2

        self._kf_update(H, y, R)
        self.pos_float = self.x[:3].copy()

        # --- razrješavanje cijelih brojeva ---
        self._resolve(D, (ri, si, S, rb, ddL), b2)
        return self.status

    def _kf_update(self, H, y, R):
        PHt = self.P @ H.T
        S = H @ PHt + R
        K = np.linalg.solve(S, PHt.T).T
        self.x = self.x + K @ y
        IKH = np.eye(len(self.x)) - K @ H
        self.P = IKH @ self.P @ IKH.T + K @ R @ K.T      # Joseph oblik (numerički stabilan)
        self.P = 0.5 * (self.P + self.P.T)

    def _resolve(self, D, geom, b2):
        ri, si, S, rb, ddL = geom
        a = D @ self.x
        # Kovarijanca DD neodređenosti + očekivani (nemodelirani) atmosferski pomak:
        # filtar s vremenom postane "presiguran" (pomak je konstantan, ne bijeli šum),
        # pa ga pri odluci o fiksu dodajemo kao donju granicu nesigurnosti.
        Qa = D @ self.P @ D.T + np.diag(b2)
        sig = np.sqrt(np.clip(np.diag(Qa), 0.0, None))
        cand = [i for i in range(len(a)) if sig[i] < AR_MAX_SIGMA_CYC]
        self.ratio = None
        self.p_boot = None
        accepted = None
        budget = [AR_MAX_LAMBDA]
        # Djelomično razrješavanje (partial AR): ako cijeli skup ne prođe testove,
        # izbaci najnesigurniju DD neodređenost (najniži / najnoviji satelit) i
        # pokušaj ponovno, dok ih ima barem MIN_FIX_DD.
        while len(cand) >= MIN_FIX_DD:
            idx = np.array(sorted(cand))
            Q_s = Qa[np.ix_(idx, idx)]
            try:
                cands, norms, p_boot = _ils_fast_or_lambda(a[idx], Q_s, sig[idx], budget)
            except np.linalg.LinAlgError:
                break
            if cands is None:                 # ADOP / budžet: ovaj skup ne može dati fiks
                cand.remove(max(cand, key=lambda i: sig[i]))
                continue
            ratio = norms[1] / max(norms[0], 1e-12) if len(norms) > 1 else np.inf
            if self.ratio is None or ratio >= RATIO_MIN:
                self.ratio = float(min(ratio, 999.0))
                self.p_boot = float(p_boot)
            if ratio >= RATIO_MIN and p_boot >= P_BOOT_MIN:
                accepted = (idx, cands[0], Q_s)
                break
            cand.remove(max(cand, key=lambda i: sig[i]))
        if accepted is None:
            self.status, self.pos, self.n_fixed = "float", self.pos_float, 0
            return
        cand, z, Q_s = accepted
        r = a[cand] - z

        # fiksni položaj = uvjetna procjena uz poznate cijele brojeve
        Ds = D[cand]
        PDt = self.P @ Ds.T
        gain = np.linalg.solve(Q_s, PDt.T).T              # P D^T Q^-1
        x_fix = self.x - gain @ r
        # validacija: DD fazni reziduali uz fiksne cijele brojeve moraju biti ~mm-cm
        geo, _ = self._dd_geometry(x_fix[:3], S, rb, ri[cand], si[cand])
        res = ddL[cand] - geo - LAMBDA1 * z
        rms = float(np.sqrt(np.mean(np.square(res))))
        if rms > FIX_RMS_MAX_M:
            self.bad_fix += 1
            if self.bad_fix >= MAX_BAD_FIX:
                # vjerojatno krivi (zadržani) fiks -> kreni ispočetka s neodređenostima
                self._reset_ambiguities()
            self.status, self.pos, self.n_fixed = "float", self.pos_float, 0
            return
        self.bad_fix = 0

        # fix-and-hold: zadrži prihvaćene cijele brojeve kao pseudo-mjerenje
        self._kf_update(Ds, z - Ds @ self.x, np.diag(HOLD_VAR + b2[cand]))
        self.pos = self.x[:3].copy()
        self.status = "fixed"
        self.n_fixed = int(len(cand))
        self.fixed_pairs = [(self.ids[ri[i]], self.ids[si[i]], int(z[j]))
                            for j, i in enumerate(cand)]

    def _reset_ambiguities(self):
        n = len(self.x)
        self.P[3:, :] = 0.0
        self.P[:, 3:] = 0.0
        self.P[3:, 3:] = np.eye(n - 3) * VAR_N0
        self.bad_fix = 0


class LiveRTK:
    """RTK u živoj sesiji: baza + generator mjerenja + filtar + metrike za frame.

    Sesija (web/backend/sim_session.py) brine o postavljanju baze (teren, auto
    položaj) i poziva `step` jednom po epohi kad je RTK uključen.
    """

    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)     # vlastiti RNG: ne dira glavni sim
        self.enabled = False
        self.base = None                           # ECEF baze
        self.base_auto = True                      # True = automatski postavljena
        self.base_switches = 0                     # auto-prebacivanja na bližu bazu
        self.obs_sim = CarrierPhaseSim(self.rng)
        self.filter = None
        self.cost_ms = None
        self._restart(0.0)

    def _restart(self, t):
        self.obs_sim.reset()
        self.filter = RTKFilter(self.base) if self.base is not None else None
        self.t_start = None
        self.t_first_fix = None
        self.epochs = 0
        self.fixed_epochs = 0
        self.n_common = 0
        self.last_status = "none"

    def set_base(self, ecef, auto, t=0.0):
        self.base = np.asarray(ecef, dtype=float)
        self.base_auto = bool(auto)
        self._restart(t)

    def restart(self, t=0.0):
        """Rover premješten / sesija promijenjena -> nove neodređenosti, novo mjerenje TTF-a."""
        self._restart(t)

    def baseline_m(self, rover):
        if self.base is None or rover is None:
            return None
        return float(np.linalg.norm(np.asarray(rover) - self.base))

    def step(self, t, satellites, rover, kinematic, los_ok=None, jam_ok=None):
        """Jedna epoha. satellites: upaljeni sateliti (objekti s current_pos,
        broadcast_pos, system, sat_id); rover: PRAVA pozicija (ECEF).
        los_ok(sat_positions_list) -> bool maska vidljivosti preko terena (rover);
        jam_ok(list of (sid, pos)) -> skup sat_id koji prežive ometanje."""
        import time as _time
        t0 = _time.perf_counter()
        if self.base is None or rover is None or self.filter is None:
            return None
        rover = np.asarray(rover, dtype=float)
        mask = np.radians(LIVE_MASK_DEG)
        sats_rtk = [s for s in satellites if s.system in RTK_SYSTEMS]
        cand = []
        if sats_rtk:
            sp = np.array([s.current_pos for s in sats_rtk], dtype=float)
            el_r = _elev_vec(rover, sp)
            el_b = _elev_vec(self.base, sp)
            cand = [(s, float(e)) for s, e, eb in zip(sats_rtk, el_r, el_b)
                    if e >= mask and eb >= mask]
        if cand and los_ok is not None:
            ok = los_ok([s.current_pos for s, _ in cand])
            cand = [c for c, k in zip(cand, ok) if k]
        if cand and jam_ok is not None:
            keep = jam_ok([(s.sat_id, s.current_pos) for s, _ in cand])
            cand = [c for c in cand if c[0].sat_id in keep]
        self.n_common = len(cand)

        baseline = float(np.linalg.norm(rover - self.base))
        sats = [(s.sat_id, s.system, s.current_pos, el, float(getattr(s, "user_clock_offset_m", 0.0)))
                for s, el in cand]
        raw = self.obs_sim.observe(sats, rover, self.base, baseline)
        obs = {}
        sat_pos = {}
        el = {}
        for s, e in cand:
            o = raw[s.sat_id]
            o["system"] = s.system
            obs[s.sat_id] = o
            sat_pos[s.sat_id] = np.asarray(getattr(s, "broadcast_pos", s.current_pos), dtype=float)
            el[s.sat_id] = e

        if self.t_start is None:
            self.t_start = float(t)
        status = self.filter.step(obs, sat_pos, el, kinematic)
        self.epochs += 1
        if status == "fixed":
            self.fixed_epochs += 1
            if self.t_first_fix is None:
                self.t_first_fix = float(t)
        self.last_status = status
        dt_ms = (_time.perf_counter() - t0) * 1000.0
        self.cost_ms = dt_ms if self.cost_ms is None else self.cost_ms + 0.2 * (dt_ms - self.cost_ms)
        return status

    def report(self, rover, t):
        """Sažetak za frame (numpy -> serialize.py ga pretvori u JSON)."""
        f = self.filter
        pos = f.pos if f is not None else None
        out = dict(
            status=self.last_status if f is not None else "none",
            base_ecef=self.base, base_auto=self.base_auto,
            base_switches=self.base_switches,
            baseline_m=self.baseline_m(rover),
            n_sats=self.n_common,
            n_dd=f.n_dd if f is not None else 0,
            n_fixed=f.n_fixed if f is not None else 0,
            ratio=f.ratio if f is not None else None,
            epochs=self.epochs, fixed_epochs=self.fixed_epochs,
            elapsed_s=(float(t) - self.t_start) if self.t_start is not None else 0.0,
            time_to_fix_s=(self.t_first_fix - self.t_start) if self.t_first_fix is not None else None,
            cost_ms=self.cost_ms,
            pos_ecef=pos, error_m=None, error_h_m=None, error_v_m=None, float_error_m=None,
        )
        if rover is not None and pos is not None:
            rover = np.asarray(rover, dtype=float)
            d = pos - rover
            up = rover / np.linalg.norm(rover)
            dv = float(np.dot(d, up))
            out["error_m"] = float(np.linalg.norm(d))
            out["error_v_m"] = abs(dv)
            out["error_h_m"] = float(np.linalg.norm(d - dv * up))
        if rover is not None and f is not None and f.pos_float is not None:
            out["float_error_m"] = float(np.linalg.norm(f.pos_float - np.asarray(rover)))
        return out


def main():
    p = argparse.ArgumentParser(description="Carrier-phase RTK demo (cm-precizno).")
    p.add_argument("--lat", type=float, default=45.815, help="rover širina [°]")
    p.add_argument("--lon", type=float, default=15.982, help="rover dužina [°]")
    p.add_argument("--alt", type=float, default=120.0)
    p.add_argument("--base-east-km", type=float, default=5.0, help="baza istočno od rovera [km]")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--dt", type=float, default=30.0, help="razmak epoha [s]")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    # baza pomaknuta istočno za nekoliko km (kratka baza)
    dlon = (args.base_east_km * 1000.0) / (6378137.0 * np.cos(np.radians(args.lat))) * (180.0 / np.pi)
    res = rtk_solve((args.lat, args.lon, args.alt),
                    (args.lat, args.lon + dlon, args.alt),
                    n_epochs=args.epochs, dt_epoch=args.dt, seed=args.seed)
    if res is None:
        print("Premalo zajedničkih satelita kroz sve epohe — povećaj epochs/dt ili smanji mask.")
        return

    print("Carrier-phase RTK")
    print("-" * 44)
    print(f"Baseline (baza-rover):    {res['baseline_m']/1000:8.2f} km")
    print(f"Zajednički sateliti:      {res['n_common']:8d}")
    print(f"Epoha:                    {res['n_epochs']:8d}")
    print(f"Integer ambiguity fixed:  {'DA' if res['ar_success'] else 'NE':>8}")
    print("-" * 44)
    print(f"Float rješenje:           {res['float_err_m']:8.3f} m")
    print(f"Fixed rješenje:           {res['fixed_err_m']:8.3f} m   (RTK)")
    print(f"(kodno rješenje je reda ~desetci m — vidi benchmark.py)")


if __name__ == "__main__":
    main()
