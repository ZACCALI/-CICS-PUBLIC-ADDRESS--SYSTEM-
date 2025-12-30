import subprocess
import time
import os

def set_volume_max(card_id):
    print(f"\n--- FORCING VOLUME MAX ON CARD {card_id} ---")
    # List of common mixer control names for USB Audio devices
    controls = ["Speaker", "PCM", "Master", "Headphone", "Playback", "Mic", "Auto Gain Control"]
    
    found_any = False
    for control in controls:
        try:
            # 1. Try to set volume to 100%
            # amixer -c [id] set [Control] 100%
            cmd_vol = ['amixer', '-c', str(card_id), 'set', control, '100%']
            result = subprocess.run(cmd_vol, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"  [OK] Set '{control}' to 100%")
                found_any = True
            
            # 2. Try to Unmute
            # amixer -c [id] set [Control] unmute
            cmd_mute = ['amixer', '-c', str(card_id), 'set', control, 'unmute']
            subprocess.run(cmd_mute, capture_output=True, text=True)
            
        except Exception as e:
            pass

    if not found_any:
        print(f"  [WARNING] No standard controls found for Card {card_id}. It might strictly be a 'Plug' device with no software mixer.")

def play_test_tone(card_id):
    print(f"  -> Testing Beep on Card {card_id}...")
    device = f"plughw:{card_id},0"
    try:
        # Use SoX to generate a synth tone
        env = os.environ.copy()
        env["AUDIODEV"] = device
        subprocess.run(['play', '-q', '-n', 'synth', '3', 'sine', '440'], env=env, check=True)
        print(f"  [SUCCESS] Command finished for Card {card_id}")
    except Exception as e:
        print(f"  [ERROR] Play command failed: {e}")

if __name__ == "__main__":
    print("=== FIXING AUDIO LEVELS ===")
    
    # Target Card IDs from previous test
    targets = [2, 3]
    
    for card in targets:
        set_volume_max(card)
        play_test_tone(card)
        time.sleep(1)

    print("\n=== DIAGNOSTIC COMPLETE ===")
    print("If you heard sound on BOTH now, the issue was just the volume/mute setting.")
    print("If one is STILL silent, try swapping the USB ports physically.")
