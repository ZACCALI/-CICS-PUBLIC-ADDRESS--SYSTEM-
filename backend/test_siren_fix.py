import sys
import os
import time
import threading

# Ensure we can import backend modules
sys.path.append(os.path.join(os.getcwd()))

from api.audio_service import audio_service

def test_siren_lifecycle():
    print("--- Testing Siren Lifecycle ---")
    
    # 1. Start Siren
    print("Starting Siren at low volume...")
    audio_service.play_siren()
    audio_service.set_siren_volume(0.1)
    
    print("Siren should be playing at 0.1 volume. Waiting 5s...")
    time.sleep(5)
    
    # 2. Ramp Volume
    print("Ramping volume to 0.6 over 5s...")
    audio_service.ramp_siren_volume(0.6, 5.0)
    
    print("Waiting 7s for ramp to complete and stay high...")
    time.sleep(7)
    
    # 3. Stop Siren
    print("Stopping Siren...")
    audio_service.stop()
    
    print("Siren should have stopped completely. Waiting 3s to confirm no extra sweeps...")
    time.sleep(3)
    
    print("Test Complete. Check if 'play' processes are still running in your system.")

if __name__ == "__main__":
    test_siren_lifecycle()
