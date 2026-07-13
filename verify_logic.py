import numpy as np
from utils import lla_to_ecef, ecef_to_lla
from physics_engine import get_orbital_period, R_EARTH

def test_conversions():
    print("Testing Coordinate Conversions...")
    test_cases = [
        (0, 0, 0),        # Equator, Prime Meridian
        (45, 45, 1000),   # Random point
        (-90, 0, 0),      # South Pole
        (0, 180, 20200000)# GPS Altitude
    ]
    
    for lat, lon, alt in test_cases:
        x, y, z = lla_to_ecef(lat, lon, alt)
        lat2, lon2, alt2 = ecef_to_lla(x, y, z)
        
        np.testing.assert_allclose([lat, lon, alt], [lat2, lon2, alt2], atol=1e-7)
        print(f"  OK: LLA({lat}, {lon}, {alt}) -> ECEF({x:.1f}, {y:.1f}, {z:.1f})")

def test_orbits():
    print("\nTesting Orbital Mechanics...")
    a = R_EARTH + 20200000
    from physics_engine import get_orbital_period
    period = get_orbital_period(a)
    period_hours = period / 3600
    print(f"  GPS Orbital Period (calculated): {period_hours:.2f} hours")
    # Should be ~11.97 hours
    assert 11.9 < period_hours < 12.1
    print("  OK: Orbital period is correct.")

def test_relativity():
    print("\nTesting Relativistic Effects...")
    a = R_EARTH + 20200000
    from physics_engine import get_relativistic_drift_rate
    drift_rate = get_relativistic_drift_rate(a)
    
    # Drift in seconds per day
    drift_per_day = drift_rate * 86400
    drift_micros = drift_per_day * 1e6
    
    print(f"  Drift rate: {drift_rate:e}")
    print(f"  Drift per day: {drift_micros:.2f} microseconds")
    
    # GPS expected value is ~38 microseconds per day (45 GR - 7 SR)
    assert 35 < drift_micros < 42
    print("  OK: Relativistic drift matches GPS theory.")

if __name__ == "__main__":
    try:
        import numpy as np
        test_conversions()
        test_orbits()
        test_relativity()
        print("\nAll internal logic tests PASSED.")
    except ImportError:
        print("Numpy not found. Skipping tests. Please install dependencies.")
    except Exception as e:
        print(f"Tests FAILED: {e}")
