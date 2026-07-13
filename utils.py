import numpy as np

def lla_to_ecef(lat, lon, alt, radius=6371000.0):
    """
    Converts Latitude, Longitude, Altitude (LLA) to Earth-Centered, Earth-Fixed (ECEF) coordinates.
    Assumes a spherical Earth for Phase 1.
    
    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        alt: Altitude in meters.
        radius: Radius of the planet in meters.
        
    Returns:
        (x, y, z) in meters.
    """
    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    
    r = radius + alt
    x = r * np.cos(lat_rad) * np.cos(lon_rad)
    y = r * np.cos(lat_rad) * np.sin(lon_rad)
    z = r * np.sin(lat_rad)
    
    return x, y, z

def ecef_to_lla(x, y, z, radius=6371000.0):
    """
    Converts ECEF to LLA.
    Assumes a spherical Earth for Phase 1.
    
    Args:
        x, y, z: Coordinates in meters.
        radius: Radius of the planet in meters.
        
    Returns:
        (lat, lon, alt) in degrees and meters.
    """
    r = np.sqrt(x**2 + y**2 + z**2)
    
    lat = np.degrees(np.arcsin(z / r))
    lon = np.degrees(np.arctan2(y, x))
    alt = r - radius
    
    return lat, lon, alt

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
