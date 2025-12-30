import os
import re
import subprocess
import threading
import time

def list_cards():
    print("--- DETECTED SOUND CARDS (aplay -l) ---")
    try:
        result = subprocess.check_output(['aplay', '-l'], text=True)
        print(result)
        
        # Regex to find card numbers
        cards = []
        for line in result.split('\n'):
            if line.startswith('card'):
                # Format: card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]
                match = re.search(r'card (\d+):', line)
                if match:
                    card_id = int(match.group(1))
                    if card_id not in cards:
                        cards.append(card_id)
        return cards
    except Exception as e:
        print(f"Error running aplay: {e}")
        return []

def play_tone(card_id, frequency=440, duration=1):
    print(f"Testing Card {card_id}...")
    device = f"plughw:{card_id},0"
    try:
        # Try SoX first
        cmd = ['play', '-n', 'synth', str(duration), 'sine', str(frequency)]
        env = os.environ.copy()
        env["AUDIODEV"] = device
        subprocess.run(cmd, env=env, stderr=subprocess.DEVNULL, check=True)
        print(f"  [SUCCESS] Sound sent to Card {card_id} (SoX)")
        return True
    except:
        try:
            # Fallback to speaker-test (common on Pi)
            print(f"  [INFO] SoX failed, trying speaker-test on {device}...")
            cmd = ['speaker-test', '-D', device, '-t', 'sine', '-f', str(frequency), '-l', '1']
            subprocess.run(cmd, stderr=subprocess.DEVNULL, timeout=duration+1)
            print(f"  [SUCCESS] Sound sent to Card {card_id} (speaker-test)")
            return True
        except Exception as e:
            print(f"  [FAILED] Could not play on Card {card_id}: {e}")
            return False

def main():
    print("=== MULTI-ZONE HARDWARE TEST ===")
    cards = list_cards()
    print(f"Found IDs: {cards}")
    print("\n--- SEQUENTIAL TEST ---")
    for cid in cards:
        play_tone(cid)
        time.sleep(0.5)
        
    print("\n--- SIMULTANEOUS TEST (ALL CARDS) ---")
    threads = []
    for cid in cards:
        t = threading.Thread(target=play_tone, args=(cid, 880, 2))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    print("\n=== TEST COMPLETE ===")
    print("If you heard sound on all speakers during the sequential test, your hardware is working.")
    print("Update 'backend/zones_config.json' with the 'card X' numbers you see above.")

if __name__ == "__main__":
    main()
