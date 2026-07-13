import numpy as np
from satellite import WalkerDeltaConstellation
from receiver import Receiver
from utils import lla_to_ecef, ecef_to_lla
from physics_engine import C

def test_receiver_functionality():
    print("--- Receiver Signal Test ---")
    constellation = WalkerDeltaConstellation()
    
    # 1. Place receiver at a known location (e.g., Zagreb, Croatia)
    lat, lon, alt = 45.8150, 15.9819, 120.0
    pos = np.array(lla_to_ecef(lat, lon, alt))
    receiver = Receiver(pos)
    
    print(f"Receiver placed at: LLA({lat}, {lon}, {alt})")
    
    # 2. Simulate for a few timestamps
    for t in [0, 3600, 7200]: # Every hour
        print(f"\nSimulating at T = {t} seconds...")
        constellation.update_all(t)
        signals = receiver.receive_signals(constellation, t)
        
        print(f"  Visible Satellites: {len(signals)}")
        
        if signals:
            # Show info for the first 3 signals
            for sig in signals[:3]:
                true_dist = sig['true_dist']
                pseudorange = sig['pseudorange']
                error = pseudorange - true_dist
                
                print(f"  - {sig['sat_id']}:")
                print(f"      True Dist:   {true_dist/1000:.3f} km")
                print(f"      Pseudorange: {pseudorange/1000:.3f} km")
                print(f"      Error:       {error:.3f} m (Clock drift effect)")

if __name__ == "__main__":
    test_receiver_functionality()
