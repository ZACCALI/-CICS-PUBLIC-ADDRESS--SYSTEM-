import os
import subprocess
import threading
import platform
import uuid
import time
import logging
import json
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AudioService:
    def __init__(self):
        self.current_process = None
        self.stream_process = None
        self._lock = threading.Lock()
        self.stream_lock = threading.Lock()
        self.proc_lock = threading.Lock()
        self.active_processes = []
        
        # SIREN STATE
        self._siren_active = False
        self._siren_volume = 0.3
        self._siren_thread = None
        self._siren_stop_event = threading.Event()
        
        # Paths
        self.root_dir = Path(__file__).resolve().parent.parent
        self.base_dir = self.root_dir / "piper_tts"
        self.system_sounds_dir = self.root_dir / "system_sounds"
        
        # Piper Setup
        self.os_type = platform.system()
        self.piper_exe = self._find_piper_executable()
        self.voices = self._scan_voices()
        
        # ZONE CONFIGURATION
        self.zones_config = self._load_zones_config()
        
        if not self.piper_exe:
            print("[AudioService] Warning: Piper TTS not found. Using System Fallback.")

    def _track_process(self, proc):
        with self.proc_lock:
            self.active_processes.append(proc)

    def _untrack_process(self, proc):
        with self.proc_lock:
            if proc in self.active_processes:
                self.active_processes.remove(proc)

    def _load_zones_config(self):
        """Loads zone mapping from zones_config.json"""
        try:
            config_path = Path(__file__).resolve().parent.parent / "zones_config.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    print(f"[AudioService] Loaded zones from {config_path}")
                    return json.load(f)
        except Exception as e:
            print(f"[AudioService] Failed to load zones: {e}")
        return {}

    def _find_piper_executable(self):
        """Finds the piper executable."""
        if not self.base_dir.exists():
            return None
            
        exe_name = "piper.exe" if self.os_type == "Windows" else "piper"
        
        # Check specific locations
        paths = [
            self.base_dir / exe_name,
            self.base_dir / "piper" / exe_name
        ]
        
        for p in paths:
            if p.exists() and p.is_file():
                return str(p)
                
        # Recursive fallback
        for path in self.base_dir.rglob(exe_name):
            if path.is_file():
                return str(path)
            
        return None

    def _scan_voices(self):
        """Scans for available .onnx voice models."""
        voices = {}
        if not self.base_dir.exists():
            return voices

        for onnx_file in self.base_dir.rglob("*.onnx"):
            name = onnx_file.stem
            voices[name] = str(onnx_file)
            
        # Assign aliases with priority
        if "en_US-amy-medium" in voices:
            voices["female"] = voices["en_US-amy-medium"]
        elif "en_US-lessac-medium" in voices:
             voices["female"] = voices["en_US-lessac-medium"]
             
        if "en_US-ryan-medium" in voices:
            voices["male"] = voices["en_US-ryan-medium"]
            
        return voices

    def _generate_piper_audio(self, text, voice_key="female"):
        """Generates WAV file using Piper. Returns path to WAV or None."""
        if not self.piper_exe or voice_key not in self.voices:
            return None
            
        model_path = self.voices[voice_key]
        output_file = self.base_dir / f"tts_{uuid.uuid4().hex}.wav"
        
        try:
            cmd = [self.piper_exe, "--model", model_path, "--output_file", str(output_file)]
            
            process = subprocess.Popen(
                cmd, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate(input=text)
            
            if process.returncode == 0 and output_file.exists():
                return str(output_file)
            else:
                print(f"[AudioService] Piper Error: {stderr}")
                return None
        except Exception as e:
            print(f"[AudioService] Piper Exception: {e}")
            return None

    def play_announcement(self, intro_path, text, voice="female", zones=[], skip_stop=False):
        """Plays Intro + TTS on specific zones"""
        if not skip_stop:
            self.stop()
        print(f"[AudioService] Announcement: '{text}' -> Zones: {zones}")
        
        # 1. Generate TTS
        wav_path = self._generate_piper_audio(text, voice)
        if not wav_path:
            # System Fallback (Windows only usually)
            self.play_text(text, voice) 
            return

        # 2. Determine Output Devices
        target_cards = self._get_target_cards(zones)
        
        # 3. Play on Targets
        self._play_multizone(intro_path, wav_path, target_cards)

    def _get_target_cards(self, zones):
        """Maps logical zones (names) to ALSA card IDs"""
        cards = set()
        
        print(f"[AudioService] Mapping Zones to Cards: {zones}")
        
        # If 'All Zones' or empty, play on all relevant cards
        if not zones or "All Zones" in zones:
            for v in self.zones_config.values():
                if isinstance(v, list): cards.update(v)
                else: cards.add(v)
            if not cards: 
                print("[AudioService] No zones found in config, defaulting to Card 2 (Pi Speakers)")
                cards.add(2) # Force Pi Speakers instead of HDMI (0)
            print(f"[AudioService] Targeted All Cards: {list(cards)}")
            return list(cards)

        # Specific Zones
        for z in zones:
            # Fuzzy match or exact match from config
            found = False
            for config_name, card_id in self.zones_config.items():
                if z.lower() in config_name.lower():
                    if isinstance(card_id, list): cards.update(card_id)
                    else: cards.add(card_id)
                    found = True
            if not found:
                print(f"[AudioService] Warning: Zone '{z}' not found in zones_config.json")
        
        if not cards: 
            print("[AudioService] Warning: No valid cards found for zones, defaulting to Card 2")
            cards.add(2) 
            
        print(f"[AudioService] Final Card Selection: {list(cards)}")
        return list(cards)

    def _play_multizone(self, intro, body, card_ids, start_time=0):
        """Plays audio sequence on list of cards (Linux) or default (Windows)"""
        
        if self.os_type == "Windows":
            # Windows: Just play on default (Development Mode)
            print("[AudioService] Windows Mode: Playing on Default Device")
            self._play_sequence_windows(intro, body)
            return

        # Linux / Raspberry Pi: Correct Multizone Logic
        threads = []
        for card_id in card_ids:
            t = threading.Thread(target=self._play_sequence_linux, args=(intro, body, card_id, start_time))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()

    def _play_sequence_linux(self, intro, body, card_id, start_time=0):
        """Plays Intro (Optional) -> Body on specific ALSA card using SoX (Preferred) or Aplay"""
        
        # Check for SoX
        has_sox = False
        try:
            subprocess.run(['which', 'play'], stdout=subprocess.DEVNULL, check=True)
            has_sox = True
        except: pass

        device = f"plughw:{card_id},0"
        
        try:
            if has_sox:
                # SoX Volume (0.9 = 90%)
                env = os.environ.copy()
                env["AUDIODEV"] = device
                print(f"[AudioService] Playing via SoX (Vol: 0.9, Seek: {start_time}s) on {device}")
                
                # 1. Intro (Optional)
                if intro:
                    p = subprocess.Popen(['play', '-v', '3.0', intro], env=env)
                    self._track_process(p)
                    p.wait()
                    self._untrack_process(p)
                
                # 2. Body
                if body:
                    cmd = ['play', '-v', '3.0', body]
                    if start_time > 0:
                        cmd.extend(['trim', str(start_time)])
                    p = subprocess.Popen(cmd, env=env)
                    self._track_process(p)
                    p.wait()
                    self._untrack_process(p)
            else:
                # Fallback to Aplay (Does not support precise trim easily)
                print(f"[AudioService] Playing via Aplay on {device}")
                if intro:
                    subprocess.run(['aplay', '-D', device, intro], check=True)
                if body:
                    subprocess.run(['aplay', '-D', device, body], check=True)
                
        except Exception as e:
            print(f"[AudioService] Linux Playback Error on Card {card_id}: {e}")

    def _play_sequence_windows(self, intro, body):
        """Windows Powershell sequence"""
        safe_intro = str(intro).replace("'", "''")
        safe_body = str(body).replace("'", "''")
        
        ps_script = f"""
        Add-Type -AssemblyName PresentationCore, PresentationFramework;
        $p = New-Object System.Windows.Media.MediaPlayer;
        $p.Open('{safe_intro}');
        $attempts = 20; 
        while (-not $p.NaturalDuration.HasTimeSpan -and $attempts -gt 0) {{ Start-Sleep -Milliseconds 100; $attempts--; }}
        $p.Play();
        if ($p.NaturalDuration.HasTimeSpan) {{
            while ($p.Position -lt $p.NaturalDuration.TimeSpan) {{ Start-Sleep -Milliseconds 100; }}
        }} else {{ Start-Sleep -Seconds 2; }}
        $p.Close();
        
        (New-Object Media.SoundPlayer '{safe_body}').PlaySync();
        """
        self._run_command(['powershell', '-c', ps_script])

    def play_text(self, text: str, voice: str = "female"):
        """Simple text playback (Testing/Emergency)"""
        self.stop()
        wav = self._generate_piper_audio(text, voice)
        if wav:
            # Default to Card 0 for simple tests
            if self.os_type == "Windows":
                 self.play_file(wav)
            else:
                 subprocess.run(['aplay', '-D', 'plughw:0,0', wav])
        else:
            print("[AudioService] Failed to generate TTS.")

    def play_broadcast_chunk(self, file_path, zones):
        # This is now legacy/unused for raw streaming but kept for safety
        pass

    def start_streaming(self, zones):
        """Initializes a persistent aplay pipe for low-latency streaming"""
        self.stop_streaming() # Only stop existing stream, don't kill the chime!
        target_cards = self._get_target_cards(zones)
        if not target_cards: return
        
        # For simplicity, we stream to the first active card in realtime mode
        # Multiple card streaming with one pipe requires 'alsaloop' or 'dmix', 
        # but for individual cards, we'll target the first one.
        card_id = target_cards[0]
        device = f"plughw:{card_id},0"
        
        with self.stream_lock:
            try:
                # Use SoX 'play' instead of 'aplay' to get volume control (-v)
                # -t raw: reading raw PCM
                # -r 16k: 16kHz
                # -e signed-integer: PCM format
                # -b 16: 16-bit
                # -c 1: Mono
                # -: read from stdin
                print(f"[AudioService] Starting Stream Pipe on {device} (Vol: 0.9, 16kHz)")
                env = os.environ.copy()
                env["AUDIODEV"] = device
                self.stream_process = subprocess.Popen(
                    ['play', '-q', '-v', '0.9', '-t', 'raw', '-r', '16000', '-e', 'signed-integer', '-b', '16', '-c', '1', '-'],
                    stdin=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    env=env
                )
            except Exception as e:
                print(f"[AudioService] Failed to start stream pipe: {e}")

    def feed_stream(self, pcm_data):
        """Feeds raw PCM bytes into the open audio pipe"""
        if self.stream_process and self.stream_process.stdin:
            try:
                self.stream_process.stdin.write(pcm_data)
                self.stream_process.stdin.flush()
            except Exception as e:
                print(f"[AudioService] Stream Feed Error: {e}")
                self.stop_streaming()

    def stop_streaming(self):
        """Closes the streaming pipe"""
        with self.stream_lock:
            if self.stream_process:
                print("[AudioService] Closing Stream Pipe")
                try:
                    self.stream_process.stdin.close()
                    self.stream_process.terminate()
                except: pass
                self.stream_process = None

    def play_chime_sync(self, zones):
        """Plays the intro chime on specified zones. Blocks until finished."""
        target_cards = self._get_target_cards(zones)
        intro_path = self.system_sounds_dir / "intro.mp3"
        
        if not intro_path.exists():
            print(f"[AudioService] Chime skipped: {intro_path} not found")
            return

        abs_intro = str(intro_path.absolute())

        threads = []
        for card_id in target_cards:
            def play_on_card(cid):
                device = f"plughw:{cid},0"
                try:
                    env = os.environ.copy()
                    env["AUDIODEV"] = device
                    # Play chime at safe volume for clarity
                    subprocess.run(['play', '-q', '-v', '0.9', intro_path], env=env, stderr=subprocess.DEVNULL)
                except:
                    # Fallback
                    subprocess.run(['aplay', '-D', device, intro_path], stderr=subprocess.DEVNULL)

            t = threading.Thread(target=play_on_card, args=(card_id,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

    def play_siren(self, zones=None):
        """Plays a synthetic emergency siren on specified zones (Pi Speakers)"""
        with self._lock:
            if self._siren_active:
                return # Already playing
            self._siren_active = True
            self._siren_stop_event.clear()
            self._siren_volume = 0.01 # Extremely low start to prevent blast
        
        target_cards = self._get_target_cards(zones)
        print(f"[AudioService] Starting Emergency Siren on cards: {target_cards}")
        
        def run_siren():
            while not self._siren_stop_event.is_set():
                threads = []
                for card_id in target_cards:
                    def play_on_card(cid):
                        device = f"plughw:{cid},0"
                        env = os.environ.copy()
                        env["AUDIODEV"] = device
                        # SoX Synth: 5 second sweep from 600Hz to 1200Hz
                        try:
                            # Use variable volume
                            vol = self._siren_volume
                            # Shorten burst to 1 second for faster volume response
                            p = subprocess.Popen(['play', '-q', '-v', str(vol), '-n', 'synth', '1', 'sine', '600:1200'], 
                                           env=env, stderr=subprocess.DEVNULL)
                            self._track_process(p)
                            p.wait()
                            self._untrack_process(p)
                        except: pass

                    t = threading.Thread(target=play_on_card, args=(card_id,))
                    threads.append(t)
                    t.start()
                
                for t in threads:
                    t.join()
            
            print("[AudioService] Siren thread exiting.")

        self._siren_thread = threading.Thread(target=run_siren, daemon=True)
        self._siren_thread.start()

    def set_siren_volume(self, volume: float):
        """Directly sets the siren volume (0.0 to 1.0)"""
        with self._lock:
            self._siren_volume = max(0.0, min(1.0, volume))
            print(f"[AudioService] Siren volume set to: {self._siren_volume}")

    def ramp_siren_volume(self, target: float, duration: float = 5.0):
        """Smoothly ramps siren volume to target over duration seconds"""
        def ramp():
            start_vol = self._siren_volume
            steps = 20
            interval = duration / steps
            for i in range(1, steps + 1):
                if self._siren_stop_event.is_set():
                    break
                new_vol = start_vol + (target - start_vol) * (i / steps)
                self.set_siren_volume(new_vol)
                time.sleep(interval)
        
        threading.Thread(target=ramp, daemon=True).start()

    def play_background_music(self, file_path: str, zones: list = None, start_time=0):
        """Plays background music asynchronously on selected zones"""
        self.stop()
        target_cards = self._get_target_cards(zones)
        
        # Run in a separate thread to avoid blocking the Controller
        def daemon_play():
            self._play_multizone(None, file_path, target_cards, start_time=start_time)
            
        t = threading.Thread(target=daemon_play, daemon=True)
        t.start()

    def _play_single_file_linux(self, file_path, card_id):
        """Plays a single file on a specific card"""
        device = f"plughw:{card_id},0"
        try:
             # Try SoX first for volume/mixing
             env = os.environ.copy()
             env["AUDIODEV"] = device
             p = subprocess.Popen(['play', '-v', '0.9', file_path], env=env, stderr=subprocess.DEVNULL)
             self._track_process(p)
             p.wait()
             self._untrack_process(p)
        except:
             # Fallback to aplay
             try:
                subprocess.run(['aplay', '-D', device, file_path], check=True, stderr=subprocess.DEVNULL)
             except Exception as e:
                print(f"[AudioService] Playback failed on card {card_id}: {e}")


    def play_intro_async(self, file_path: str):
         """Plays intro asynchronously (Windows only visual supported, Linux fire-and-forget)"""
         self.stop()
         if self.os_type == "Windows":
             safe_path = str(file_path).replace("'", "''")
             ps_script = f"""
             Add-Type -AssemblyName PresentationCore, PresentationFramework;
             $p = New-Object System.Windows.Media.MediaPlayer;
             $p.Open('{safe_path}');
             $p.Play();
             Start-Sleep -Seconds 3;
             $p.Close();
             """
             self._run_command(['powershell', '-c', ps_script])
         else:
             # Linux Async
             subprocess.Popen(['aplay', '-D', 'plughw:0,0', file_path])

    def play_file(self, file_path: str):
        self.stop()
        if self.os_type == "Windows":
            safe_path = str(file_path).replace("'", "''")
            self._run_command(['powershell', '-c', f"(New-Object Media.SoundPlayer '{safe_path}').PlaySync()"])
        else:
            subprocess.run(['aplay', '-D', 'plughw:0,0', file_path])

    def stop(self):
        with self._lock:
            if self.current_process:
                try: self.current_process.terminate()
                except: pass
                self.current_process = None
            
            # Stop Siren
            self._siren_stop_event.set()
            self._siren_active = False
            
            # 1. Direct Process Termination
            with self.proc_lock:
                for proc in self.active_processes:
                    try:
                        print(f"[AudioService] Terminating process {proc.pid}")
                        proc.terminate()
                        # Wait briefly for termination
                        try: proc.wait(timeout=0.2)
                        except: proc.kill()
                    except: pass
                self.active_processes.clear()

            # 2. Linux Fallback: killall aplay? A bit aggressive but effective for "Stop" button.
            if self.os_type != "Windows":
                os.system("killall -q aplay")
                os.system("killall -q play")
            
            self.stop_streaming()

    def _run_command(self, command):
        """Threaded command runner for Windows"""
        def target():
            proc = None
            with self._lock:
                try:
                    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.current_process = proc
                except: return
            if proc:
                try: proc.communicate()
                except: pass
                finally:
                    with self._lock:
                        if self.current_process == proc: self.current_process = None
        threading.Thread(target=target).start()
        
audio_service = AudioService()
