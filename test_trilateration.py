import numpy as np
from satellite import WalkerDeltaConstellation
from receiver import Receiver
from utils import lla_to_ecef

def test_trilateration_accuracy():
    print("--- Trilateration Accuracy Test ---")
    constellation = WalkerDeltaConstellation()
    
    # 1. Ground Truth (e.g. London)
    lat, lon, alt = 51.5074, -0.1278, 50.0
    gt_pos = np.array(lla_to_ecef(lat, lon, alt))
    
    receiver = Receiver(gt_pos)
    
    print(f"Ground Truth: {gt_pos}")
    
    # 2. Simulate over time and solve
    for t in range(0, 3601, 1200): # Every 20 mins for an hour
        constellation.update_all(t)
        receiver.receive_signals(constellation, t)
        
        calc_pos, calc_bias = receiver.solve_position()
        
        if calc_pos is not None:
            error = np.linalg.norm(calc_pos - gt_pos)
            print(f"\nT = {t}s:")
            print(f"  Visible Satellites: {len(receiver.received_signals)}")
            print(f"  Calculated Pos:    {calc_pos}")
            print(f"  Calculated Bias:   {calc_bias*1e6:.2f} us")
            print(f"  Position Error:    {error:.4f} meters")
            
            # The error should be very small in a noise-free simulation
            # but relativity is included in pseudoranges and the solver handles it!
            assert error < 1.0 # Should be sub-meter in ideal conditions
        else:
            print(f"\nT = {t}s: Not enough satellites!")

if __name__ == "__main__":
    test_trilateration_accuracy()
