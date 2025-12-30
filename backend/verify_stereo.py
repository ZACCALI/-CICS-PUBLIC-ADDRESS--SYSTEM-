import subprocess
import os
import time

def test_channel(card_id, channel_name):
    print(f"\n--- TESTING {channel_name.upper()} CHANNEL ON CARD {card_id} ---")
    device = f"plughw:{card_id},0"
    
    # Flags for Left vs Right
    # Left = remix 1 0
    # Right = remix 0 1
    remix = ['remix', '1', '0'] if channel_name == 'left' else ['remix', '0', '1']
    
    env = os.environ.copy()
    env["AUDIODEV"] = device
    
    # Generate a tone -> apply remix
    cmd = ['play', '-n', 'synth', '2', 'sine', '440'] + remix
    
    print(f"Runnable Command: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, env=env, check=True)
        print("  [SUCCESS] Play command finished.")
    except Exception as e:
        print(f"  [ERROR] {e}")

if __name__ == "__main__":
    print("=== STEREO SEPARATION TEST ===")
    
    # Prompt for Card ID
    try:
        val = input("Enter Sound Card ID (e.g. 2): ")
        card = int(val)
    except:
        card = 2
        print("Defaulting to Card 2...")

    print(f"\n1. I will now play sound ONLY on the LEFT speaker (Library).")
    print("   The Right speaker (Admin) should be SILENT.")
    time.sleep(1)
    test_channel(card, 'left')
    
    time.sleep(1)
    
    print(f"\n2. I will now play sound ONLY on the RIGHT speaker (Admin).")
    print("   The Left speaker (Library) should be SILENT.")
    time.sleep(1)
    test_channel(card, 'right')
    
    print("\n=== TEST COMPLETE ===")
    print("Did you hear clear separation?")
    print("- YES: The code is working perfectly.")
    print("- NO (Sound on both each time): Your CABLE or AMP is Mono-bridged.")
