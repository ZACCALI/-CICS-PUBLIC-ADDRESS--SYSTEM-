
import os
import subprocess
import time

def list_cards():
    print("--- DETECTED AUDIO CARDS ---")
    try:
        # Parse /proc/asound/cards or aplay -l
        result = subprocess.run(['aplay', '-l'], capture_output=True, text=True)
        print(result.stdout)
        
        cards = []
        for line in result.stdout.split('\n'):
            if "card" in line and ":" in line:
                # card 2: ...
                try:
                    parts = line.split(":")
                    card_id = int(parts[0].replace("card", "").strip())
                    cards.append(card_id)
                except: pass
        return list(set(cards))
    except Exception as e:
        print(f"Error listing cards: {e}")
        return []

def test_play(card_id):
    device = f"plughw:{card_id},0"
    print(f"\nTesting Output on Card {card_id} ({device})...")
    
    # Method 1: Speaker-Test (Pink Noise)
    print("  1. Speaker-Test (Pink Noise)...")
    try:
        # Run for 2 seconds
        cmd = ['speaker-test', '-D', device, '-c', '2', '-l', '1', '-t', 'pink']
        p = subprocess.Popen(cmd)
        time.sleep(2)
        p.terminate()
        p.wait()
    except Exception as e:
        print(f"  [Failed] Speaker-Test: {e}")

    # Method 2: Aplay (Silence/Beep if file existed, but we'll try SOX synth)
    print("  2. SoX Synth Beep...")
    try:
        env = os.environ.copy()
        env["AUDIODEV"] = device
        # Play a 1-second sine wave at 440Hz
        subprocess.run(['play', '-n', 'synth', '1', 'sine', '440'], env=env, stderr=subprocess.PIPE)
        print("  [Success] SoX command finished (Did you hear it?)")
    except FileNotFoundError:
        print("  [Skipped] SoX (play) not found.")
    except Exception as e:
        print(f"  [Failed] SoX: {e}")

if __name__ == "__main__":
    cards = list_cards()
    if not cards:
        print("NO AUDIO CARDS FOUND! Check hardware/drivers.")
    else:
        print(f"Found Cards: {cards}")
        for c in cards:
            test_play(c)
