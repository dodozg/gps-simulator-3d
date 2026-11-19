"""Parseri za PRAVE GNSS podatke: RINEX opažanja, RINEX navigacija i SP3 orbite.

Čisti Python + numpy (bez novih ovisnosti). Podržano:

* **RINEX opažanja** v2.10/2.11 i v3.0x — sve oznake mjerenja se čuvaju, a
  pomoćna `RinexObs.gps_l1()` vraća normalizirani GPS L1 skup
  `{'C1': pseudoudaljenost [m], 'L1': faza [ciklusi], 'S1': SNR [dB-Hz]}`
  (v2: C1 → P1 kao rezerva; v3: C1C → C1W/C1P/C1X…). Event zastavice 2–5
  (umetnuti zapisi zaglavlja, npr. "RINEX FILE SPLICE") se preskaču, zastavica
  6 (cycle slip zapisi) također; epoha sa zastavicom 1 (power failure) se
  zadržava.
* **RINEX navigacija** (GPS broadcast efemeride) v2 i v3 + Klobuchar
  koeficijenti iz zaglavlja (v2 `ION ALPHA/BETA`, v3 `IONOSPHERIC CORR GPSA/GPSB`).
  U miješanim v3 datotekama ne-GPS zapisi se preskaču (GLONASS/SBAS imaju 3,
  ostali 7 linija orbite).
* **SP3-c/d** precizne orbite (samo za VALIDACIJU broadcast efemerida, vidi
  tests/test_realdata.py) — pozicije [m] i satovi [s].

Vrijeme se svugdje prikazuje kao **GPS sekunde od GPS epohe 1980-01-06 00:00**
(float; dvostruka preciznost daje ~0.2 µs na 2^31 s, tj. < 1 mm gibanja satelita).

Sigurnost: datoteke se samo ČITAJU kao tekst; ništa iz njih se ne izvršava.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

import numpy as np

from ephemeris import Ephemeris

GPS_EPOCH = _dt.date(1980, 1, 6)
SEC_PER_WEEK = 604800.0

# Redoslijed preferencije za GPS L1 C/A kôd / fazu / SNR u RINEX v3 (C = C/A,
# W/P = P(Y) (semi-codeless), X = L1C kombinirani, S/L = L1C data/pilot).
_V3_L1_PREF = {
    "C1": ("C1C", "C1W", "C1P", "C1X", "C1S", "C1L"),
    "L1": ("L1C", "L1W", "L1P", "L1X", "L1S", "L1L"),
    "S1": ("S1C", "S1W", "S1P", "S1X", "S1S", "S1L"),
}
_V2_L1_PREF = {"C1": ("C1", "P1"), "L1": ("L1",), "S1": ("S1",)}


def gps_seconds(year, month, day, hour=0, minute=0, sec=0.0):
    """Kalendarski datum (GPS vremenska skala) -> GPS sekunde od 1980-01-06."""
    days = _dt.date(int(year), int(month), int(day)).toordinal() - GPS_EPOCH.toordinal()
    return days * 86400.0 + int(hour) * 3600.0 + int(minute) * 60.0 + float(sec)


def gps_week_tow(t):
    """GPS sekunde -> (GPS tjedan, sekunde u tjednu)."""
    week = int(np.floor(t / SEC_PER_WEEK))
    return week, t - week * SEC_PER_WEEK


def gps_to_datetime(t):
    """GPS sekunde -> naivni datetime u GPS vremenskoj skali (bez prijestupnih sekundi)."""
    return _dt.datetime(1980, 1, 6) + _dt.timedelta(seconds=float(t))


def _year4(yy):
    """RINEX v2 dvoznamenkasta godina: 80–99 -> 19xx, 00–79 -> 20xx."""
    yy = int(yy)
    if yy >= 100:
        return yy
    return 1900 + yy if yy >= 80 else 2000 + yy


def _f(s):
    """Fortran broj (dopušta 'D' eksponent i prazninu) -> float; prazno -> NaN."""
    s = s.strip()
    if not s:
        return float("nan")
    return float(s.replace("D", "E").replace("d", "e"))


def _lines(src):
    """Put ili tekst -> lista linija bez znakova kraja reda (podržava CRLF)."""
    if isinstance(src, (bytes, bytearray)):
        text = src.decode("ascii", errors="replace")
    elif "\n" in src or "\r" in src:
        text = src
    else:
        with open(src, "r", encoding="ascii", errors="replace") as fh:
            text = fh.read()
    return text.splitlines()


def _norm_sat(tok, default_sys="G"):
    """'G 3' / ' 3' / 'G03' -> 'G03' (prazan sustav u v2 = GPS)."""
    tok = tok.rstrip()
    if not tok.strip():
        return None
    sys = tok[0] if tok[0].isalpha() else default_sys
    num = tok[1:] if tok[0].isalpha() or tok[0] == " " else tok
    try:
        return f"{sys}{int(num):02d}"
    except ValueError:
        return None


# =============================================================================
#  RINEX OPAŽANJA
# =============================================================================
@dataclass
class ObsHeader:
    version: float = 0.0
    sat_system: str = "G"
    marker_name: str = ""
    receiver_type: str = ""
    antenna_type: str = ""
    approx_pos: np.ndarray | None = None       # APPROX POSITION XYZ [m] (ECEF)
    antenna_delta_hen: tuple = (0.0, 0.0, 0.0)  # ANTENNA: DELTA H/E/N [m]
    obs_types: dict = field(default_factory=dict)   # sustav -> [oznake]; v2: '*' -> lista
    interval: float | None = None
    time_first_obs: float | None = None        # GPS sekunde


@dataclass
class ObsEpoch:
    t: float                        # vremenska oznaka epohe (sat PRIJEMNIKA), GPS sekunde
    flag: int                       # 0 = OK, 1 = power failure (ostale se preskaču)
    obs: dict                       # 'G03' -> {'C1': .., 'L1': .., ...} (samo prisutne vrijednosti)
    lli: dict = field(default_factory=dict)   # 'G03' -> {'L1': lli, ...} (samo ne-nula)
    ssi: dict = field(default_factory=dict)   # 'G03' -> {'L1': ssi, ...} (samo ne-nula)
    clock_offset: float | None = None          # opcionalni offset sata prijemnika [s]

    @property
    def week_tow(self):
        return gps_week_tow(self.t)


@dataclass
class RinexObs:
    header: ObsHeader
    epochs: list

    def obs_types_for(self, system):
        return self.header.obs_types.get(system, self.header.obs_types.get("*", []))

    def gps_l1(self, epoch, system="G"):
        """Normalizirani L1 skup za sustav `system`: {'G03': {'C1','L1','S1'}}.

        Sateliti bez L1 pseudoudaljenosti se izostavljaju. Ključevi 'L1'/'S1'
        postoje samo ako ih datoteka ima.
        """
        pref = _V3_L1_PREF if self.header.version >= 3.0 else _V2_L1_PREF
        out = {}
        for sat, vals in epoch.obs.items():
            if sat[0] != system:
                continue
            rec = {}
            for key, codes in pref.items():
                for c in codes:
                    v = vals.get(c)
                    if v is not None and np.isfinite(v) and v != 0.0:
                        rec[key] = v
                        break
            if "C1" in rec:
                out[sat] = rec
        return out


def _parse_obs_header(lines):
    h = ObsHeader()
    i = 0
    pending_sys, pending_n, pending = None, 0, []
    v2_types, v2_n = [], 0
    while i < len(lines):
        ln = lines[i]
        label = ln[60:].strip()
        if label == "RINEX VERSION / TYPE":
            h.version = float(ln[0:9])
            h.sat_system = (ln[40:41].strip() or "G")
        elif label == "MARKER NAME":
            h.marker_name = ln[0:60].strip()
        elif label == "REC # / TYPE / VERS":
            h.receiver_type = ln[20:40].strip()
        elif label == "ANT # / TYPE":
            h.antenna_type = ln[20:40].strip()
        elif label == "APPROX POSITION XYZ":
            xyz = [_f(ln[k:k + 14]) for k in (0, 14, 28)]
            if all(np.isfinite(xyz)) and any(xyz):
                h.approx_pos = np.array(xyz, dtype=float)
        elif label == "ANTENNA: DELTA H/E/N":
            h.antenna_delta_hen = tuple(_f(ln[k:k + 14]) for k in (0, 14, 28))
        elif label == "# / TYPES OF OBSERV":          # RINEX v2
            if not v2_types:
                v2_n = int(ln[0:6])
            for k in range(9):
                tok = ln[10 + 6 * k:12 + 6 * k].strip()
                if tok:
                    v2_types.append(tok)
            h.obs_types["*"] = v2_types[:v2_n]
        elif label == "SYS / # / OBS TYPES":          # RINEX v3
            if ln[0] != " ":
                pending_sys, pending_n, pending = ln[0], int(ln[3:6]), []
            for k in range(13):
                tok = ln[7 + 4 * k:10 + 4 * k].strip()
                if tok:
                    pending.append(tok)
            if pending_sys is not None:
                h.obs_types[pending_sys] = pending[:pending_n]
        elif label == "INTERVAL":
            h.interval = _f(ln[0:10])
        elif label == "TIME OF FIRST OBS":
            y, mo, d, hh, mi = (int(ln[k:k + 6]) for k in (0, 6, 12, 18, 24))
            h.time_first_obs = gps_seconds(y, mo, d, hh, mi, float(ln[30:43]))
        elif label == "END OF HEADER":
            return h, i + 1
        i += 1
    raise ValueError("RINEX obs: nema END OF HEADER")


def _read_values(text, n, width=16):
    """n polja (F14.3 + LLI + SSI) iz spojenog teksta -> [(val, lli, ssi)]."""
    out = []
    for k in range(n):
        f = text[k * width:(k + 1) * width]
        v = f[0:14].strip()
        val = float(v) if v else None
        lli = f[14:15].strip()
        ssi = f[15:16].strip()
        out.append((val, int(lli) if lli.isdigit() else 0, int(ssi) if ssi.isdigit() else 0))
    return out


def _store(epoch, sat, types, vals):
    rec, lli, ssi = {}, {}, {}
    for code, (v, l, s) in zip(types, vals):
        if v is None:
            continue
        rec[code] = v
        if l:
            lli[code] = l
        if s:
            ssi[code] = s
    if rec:
        epoch.obs[sat] = rec
        if lli:
            epoch.lli[sat] = lli
        if ssi:
            epoch.ssi[sat] = ssi


def _parse_obs_v2(h, lines, i):
    types = h.obs_types.get("*", [])
    nlines_per_sat = (len(types) + 4) // 5
    epochs = []
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        flag = int(ln[28:29]) if ln[28:29].strip() else 0
        nsat = int(ln[29:32]) if ln[29:32].strip() else 0
        if flag >= 2 and flag <= 5:
            i += 1 + nsat                         # nsat = broj zapisa zaglavlja koji slijede
            continue
        # popis satelita (12 po liniji, nastavak u sljedećim linijama)
        sats = []
        nl_sat = (nsat + 11) // 12
        for k in range(nl_sat):
            sl = lines[i + k]
            for j in range(12):
                if len(sats) >= nsat:
                    break
                sats.append(_norm_sat(sl[32 + 3 * j:35 + 3 * j]))
        clk = _f(ln[68:80]) if len(ln) > 68 else float("nan")
        i += nl_sat
        if flag == 6:                              # cycle slip zapisi: preskoči
            i += nsat * nlines_per_sat
            continue
        yy, mo, dd, hh, mi = (int(ln[k:k + 3]) for k in (0, 3, 6, 9, 12))
        t = gps_seconds(_year4(yy), mo, dd, hh, mi, float(ln[15:26]))
        ep = ObsEpoch(t=t, flag=flag, obs={}, clock_offset=clk if np.isfinite(clk) else None)
        for sat in sats:
            chunk = "".join(lines[i + k].ljust(80)[:80] for k in range(nlines_per_sat)
                            if i + k < len(lines))
            i += nlines_per_sat
            if sat is None:
                continue
            _store(ep, sat, types, _read_values(chunk, len(types)))
        epochs.append(ep)
    return epochs


def _parse_obs_v3(h, lines, i):
    epochs = []
    while i < len(lines):
        ln = lines[i]
        if not ln.startswith(">"):
            i += 1
            continue
        flag = int(ln[31:32]) if ln[31:32].strip() else 0
        nsat = int(ln[32:35]) if ln[32:35].strip() else 0
        i += 1
        if flag >= 2:                              # 2–5 zaglavlje, 6 cycle slip: preskoči zapise
            i += nsat
            continue
        # "> 2010 07 01 00 00  0.0000000  0 12"
        y, mo, d, hh, mi = (int(ln[2:6]), int(ln[7:9]), int(ln[10:12]),
                            int(ln[13:15]), int(ln[16:18]))
        t = gps_seconds(y, mo, d, hh, mi, float(ln[18:29]))
        clk = _f(ln[41:56]) if len(ln) > 41 else float("nan")
        ep = ObsEpoch(t=t, flag=flag, obs={}, clock_offset=clk if np.isfinite(clk) else None)
        for _ in range(nsat):
            if i >= len(lines):
                break
            sl = lines[i]
            i += 1
            sat = _norm_sat(sl[0:3])
            if sat is None:
                continue
            types = h.obs_types.get(sat[0], [])
            _store(ep, sat, types, _read_values(sl[3:].ljust(16 * len(types)), len(types)))
        epochs.append(ep)
    return epochs


def read_obs(src, max_epochs=None):
    """Pročitaj RINEX opažanja (v2.1x ili v3.0x). `src` = put ili sadržaj datoteke."""
    lines = _lines(src)
    h, i = _parse_obs_header(lines)
    if h.version >= 3.0:
        epochs = _parse_obs_v3(h, lines, i)
    else:
        epochs = _parse_obs_v2(h, lines, i)
    if max_epochs is not None:
        epochs = epochs[:max_epochs]
    return RinexObs(header=h, epochs=epochs)


# =============================================================================
#  RINEX NAVIGACIJA (GPS)
# =============================================================================
@dataclass
class NavHeader:
    version: float = 0.0
    iono_alpha: tuple | None = None   # Klobuchar α0..α3 [s, s/sc, s/sc², s/sc³]
    iono_beta: tuple | None = None    # Klobuchar β0..β3 [s, ...]
    leap_seconds: int | None = None


@dataclass
class RinexNav:
    header: NavHeader
    ephemerides: dict                 # 'G03' -> [Ephemeris, ...] (sortirano po toe)

    def all(self):
        return [e for lst in self.ephemerides.values() for e in lst]


# Imena 4 polja po "broadcast orbit" liniji (IS-GPS-200 / RINEX tablica A4).
_ORBIT_FIELDS = (
    ("iode", "crs", "delta_n", "m0"),
    ("cuc", "e", "cus", "sqrt_a"),
    ("toe_sow", "cic", "omega0", "cis"),
    ("i0", "crc", "omega", "omega_dot"),
    ("idot", "codes_l2", "week", "l2p_flag"),
    ("sv_accuracy", "health", "tgd", "iodc"),
    ("tot", "fit_interval", None, None),
)
_V3_ORBIT_LINES = {"G": 7, "E": 7, "C": 7, "J": 7, "I": 7, "R": 3, "S": 3}


def _make_ephemeris(prn, toc, clk, orbit_vals):
    d = {}
    for names, vals in zip(_ORBIT_FIELDS, orbit_vals):
        for n, v in zip(names, vals):
            if n is not None:
                d[n] = 0.0 if not np.isfinite(v) else v
    for n in ("tot", "fit_interval"):
        d.setdefault(n, 0.0)
    return Ephemeris(
        prn=prn, toc=toc, af0=clk[0], af1=clk[1], af2=clk[2],
        iode=d["iode"], crs=d["crs"], delta_n=d["delta_n"], m0=d["m0"],
        cuc=d["cuc"], e=d["e"], cus=d["cus"], sqrt_a=d["sqrt_a"],
        toe_sow=d["toe_sow"], cic=d["cic"], omega0=d["omega0"], cis=d["cis"],
        i0=d["i0"], crc=d["crc"], omega=d["omega"], omega_dot=d["omega_dot"],
        idot=d["idot"], week=int(round(d["week"])), sv_accuracy=d["sv_accuracy"],
        health=int(round(d["health"])), tgd=d["tgd"], iodc=d["iodc"],
        tot=d["tot"], fit_interval=d["fit_interval"],
    )


def _orbit_line(ln, offset):
    return [_f(ln[offset + 19 * k:offset + 19 * (k + 1)]) for k in range(4)]


def read_nav(src):
    """Pročitaj GPS navigacijsku datoteku (RINEX v2 'N' ili v3 'N' s GPS zapisima)."""
    lines = _lines(src)
    h = NavHeader()
    i = 0
    while i < len(lines):
        ln = lines[i]
        label = ln[60:].strip()
        if label == "RINEX VERSION / TYPE":
            h.version = float(ln[0:9])
        elif label == "ION ALPHA":
            h.iono_alpha = tuple(_f(ln[2 + 12 * k:14 + 12 * k]) for k in range(4))
        elif label == "ION BETA":
            h.iono_beta = tuple(_f(ln[2 + 12 * k:14 + 12 * k]) for k in range(4))
        elif label == "IONOSPHERIC CORR":
            vals = tuple(_f(ln[5 + 12 * k:17 + 12 * k]) for k in range(4))
            if ln[0:4] == "GPSA":
                h.iono_alpha = vals
            elif ln[0:4] == "GPSB":
                h.iono_beta = vals
        elif label == "LEAP SECONDS":
            try:
                h.leap_seconds = int(ln[0:6])
            except ValueError:
                pass
        elif label == "END OF HEADER":
            i += 1
            break
        i += 1

    ephs = {}
    v3 = h.version >= 3.0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        if v3:
            sys = ln[0]
            n_orb = _V3_ORBIT_LINES.get(sys, 7)
            if sys != "G":
                i += 1 + n_orb
                continue
            prn = _norm_sat(ln[0:3])
            y, mo, d, hh, mi, ss = (int(ln[4:8]), int(ln[9:11]), int(ln[12:14]),
                                    int(ln[15:17]), int(ln[18:20]), float(ln[21:23]))
            clk = [_f(ln[23 + 19 * k:42 + 19 * k]) for k in range(3)]
            off = 4
        else:
            n_orb = 7
            prn = _norm_sat("G" + ln[0:2])
            y, mo, d, hh, mi = (int(ln[k:k + 3]) for k in (2, 5, 8, 11, 14))
            y = _year4(y)
            ss = float(ln[17:22])
            clk = [_f(ln[22 + 19 * k:41 + 19 * k]) for k in range(3)]
            off = 3
        orbit = []
        for k in range(n_orb):
            orbit.append(_orbit_line(lines[i + 1 + k] if i + 1 + k < len(lines) else "", off))
        i += 1 + n_orb
        toc = gps_seconds(y, mo, d, hh, mi, ss)
        eph = _make_ephemeris(prn, toc, [0.0 if not np.isfinite(c) else c for c in clk], orbit)
        ephs.setdefault(prn, []).append(eph)
    for lst in ephs.values():
        lst.sort(key=lambda e: e.toe)
    return RinexNav(header=h, ephemerides=ephs)


# =============================================================================
#  SP3 (precizne orbite, za validaciju)
# =============================================================================
def read_sp3(src):
    """SP3-c/d -> {'G01': [(t_gps_s, xyz_m ndarray, clk_s ili NaN), ...]}.

    Pozicije su u km u datoteci (centar MASE satelita), satovi u µs
    (999999.999999 = nepoznato -> NaN). Vremenska skala se pretpostavlja GPS.
    """
    out = {}
    t = None
    for ln in _lines(src):
        if ln.startswith("*  "):
            y, mo, d, hh, mi = (int(x) for x in ln[3:31].split()[:5])
            sec = float(ln[3:31].split()[5])
            t = gps_seconds(y, mo, d, hh, mi, sec)
        elif ln.startswith("P") and t is not None:
            sat = _norm_sat(ln[1:4])
            x, y_, z = (_f(ln[4 + 14 * k:18 + 14 * k]) for k in range(3))
            clk = _f(ln[46:60])
            clk_s = clk * 1e-6 if np.isfinite(clk) and abs(clk) < 999999.0 else float("nan")
            if sat and all(np.isfinite([x, y_, z])) and (x, y_, z) != (0.0, 0.0, 0.0):
                out.setdefault(sat, []).append((t, np.array([x, y_, z]) * 1000.0, clk_s))
    return out
