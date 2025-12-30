import sys
import os
import time

# Add paths to allow imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.audio_service import AudioService

def test_logic():
    print("\n=== TESTING LOGIC: Zone Mapping ===")
    service = AudioService()
    
    # Test 1: Library
    print("\n[Input] 'Library'")
    targets = service._get_target_cards(["Library"])
    print(f"[Output] {targets}")
    
    expected = {'card': 2, 'channel': 'left'}
    
    # Check if we got the expected target (ignoring list wrapper)
    is_correct = False
    for t in targets:
        if isinstance(t, dict) and t.get('channel') == 'left':
            is_correct = True
            
    if is_correct:
        print("✅ LOGIC PASSED: Library maps to LEFT channel.")
    else:
        print("❌ LOGIC FAILED: Library did NOT map to Left Channel!")
        print("   (This means it is defaulting to Stereo, which causes the bleeding)")
        return

    print("\n=== TESTING PLAYBACK: Real Audio File ===")
    print("Playing 'intro.mp3' on Library (Left Only)...")
    print("LISTEN: Right speaker should be SILENT.")
    
    # Use internal method to test exact command logic
    intro_path = str(service.system_sounds_dir / "intro.mp3")
    service._play_sequence_linux(intro_path, None, 2, channel='left', start_time=0)
    
    print("Did it work?")

if __name__ == "__main__":
    test_logic()
