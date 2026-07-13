import numpy as np

# --- WGS-84 elipsoid ----------------------------------------------------------
# Zemlja nije kugla nego spljošteni rotacijski elipsoid. Ranije se koristila
# sferna aproksimacija (jedan radijus 6371 km) što daje geocentričnu širinu koja
# odstupa od geodetske (kakvu prikazuju karte) i do ~0.19° (~20 km na tlu).
# WGS-84 je referentni elipsoid koji koristi i pravi GPS.
WGS84_A = 6378137.0                      # velika poluos (ekvatorski radijus) [m]
WGS84_F = 1.0 / 298.257223563            # spljoštenost
WGS84_B = WGS84_A * (1.0 - WGS84_F)      # mala poluos (polarni radijus) [m]
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)     # kvadrat prve ekscentričnosti
_WGS84_EP2 = (WGS84_A**2 - WGS84_B**2) / WGS84_B**2  # kvadrat druge ekscentričnosti


def lla_to_ecef(lat, lon, alt):
    """Geodetska širina/dužina/visina (LLA) -> ECEF, na WGS-84 elipsoidu.

    Args:
        lat: Geodetska širina [°].
        lon: Geodetska dužina [°].
        alt: Visina iznad elipsoida [m].

    Returns:
        (x, y, z) u metrima.
    """
    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    sin_lat = np.sin(lat_rad)
    cos_lat = np.cos(lat_rad)

    # N = radijus zakrivljenosti u vertikalu (prime vertical)
    N = WGS84_A / np.sqrt(1.0 - WGS84_E2 * sin_lat**2)

    x = (N + alt) * cos_lat * np.cos(lon_rad)
    y = (N + alt) * cos_lat * np.sin(lon_rad)
    z = (N * (1.0 - WGS84_E2) + alt) * sin_lat

    return x, y, z


def ecef_to_lla(x, y, z):
    """ECEF -> geodetska širina/dužina/visina (LLA), na WGS-84 elipsoidu.

    Koristi Bowringovu zatvorenu formulu (bez iteracije), točnu na sub-milimetar
    za sve realne terestričke i orbitalne visine.

    Args:
        x, y, z: Koordinate u metrima.

    Returns:
        (lat, lon, alt) u stupnjevima i metrima.
    """
    lon = np.arctan2(y, x)

    p = np.sqrt(x**2 + y**2)
    if p < 1e-9:  # točka na osi rotacije (pol)
        lat = np.pi / 2.0 if z >= 0 else -np.pi / 2.0
        alt = abs(z) - WGS84_B
        return np.degrees(lat), np.degrees(lon), alt

    # Bowringova pomoćna latituda
    theta = np.arctan2(z * WGS84_A, p * WGS84_B)
    sin_t, cos_t = np.sin(theta), np.cos(theta)

    lat = np.arctan2(
        z + _WGS84_EP2 * WGS84_B * sin_t**3,
        p - WGS84_E2 * WGS84_A * cos_t**3,
    )
    sin_lat = np.sin(lat)
    N = WGS84_A / np.sqrt(1.0 - WGS84_E2 * sin_lat**2)
    alt = p / np.cos(lat) - N

    return np.degrees(lat), np.degrees(lon), alt


def format_dms(degrees, is_lat=True):
    """
    Konvertuje decimalne stepene u Degrees, Minutes, Seconds format.
    """
    direction = ""
    if is_lat:
        direction = "N" if degrees >= 0 else "S"
    else:
        direction = "E" if degrees >= 0 else "W"

    abs_deg = abs(degrees)
    d = int(abs_deg)
    m_float = (abs_deg - d) * 60
    m = int(m_float)
    s = (m_float - m) * 60

    return f"{d}°{m}'{s:.2f}\"{direction}"
