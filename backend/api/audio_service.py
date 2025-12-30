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
        self.stream_process = None # Legacy (Keep to prevent AttributeErrors if referenced elsewhere briefly)
        self.stream_processes = [] # NEW: List of open pipes for Multizone
        self._lock = threading.Lock()
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
        """Maps logical zones (names) to targets [{'card': int, 'channel': str/None}]"""
        targets = []
        seen = set()

        print(f"[AudioService] Mapping Zones: {zones}")
        
        # Helper to add unique targets
        def add_target(val):
            card = val
            channel = None
            if isinstance(val, dict):
                card = val.get('card', 2)
                channel = val.get('channel')
            
            key = (card, channel)
            if key not in seen:
                seen.add(key)
                targets.append({'card': card, 'channel': channel})

        # Logic
        if not zones or "All Zones" in zones:
            for v in self.zones_config.values():
                if isinstance(v, list):
                    for item in v: add_target(item)
                else: 
                    add_target(v)
        else:
            for z in zones:
                found = False
                for config_name, val in self.zones_config.items():
                    if z.lower() in config_name.lower():
                        if isinstance(val, list):
                            for item in val: add_target(item)
                        else:
                            add_target(val)
                        found = True
                if not found:
                     print(f"[AudioService] Warning: Zone '{z}' not found")

        if not targets:
            print("[AudioService] Defaulting to Card 2 (Stereo)")
            add_target(2)
            
        print(f"[AudioService] Final Targets: {targets}")
        return targets

    def _ensure_device_active(self, card_id):
        """Forces the card to be unmuted and at 100% volume."""
        try:
            # Common control names
            controls = ["Speaker", "PCM", "Master", "Headphone", "Playback"]
            for c in controls:
                subprocess.run(['amixer', '-c', str(card_id), 'set', c, '100%', 'unmute'], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass

    def _play_multizone(self, intro, body, targets, start_time=0):
        """Plays audio sequence on list of targets (Linux) or default (Windows)"""
        
        if self.os_type == "Windows":
            print("[AudioService] Windows Mode: Playing on Default Device")
            self._play_sequence_windows(intro, body)
            return

        # Linux / Raspberry Pi
        threads = []
        # Support legacy list of ints just in case
        clean_targets = []
        for t in targets:
            if isinstance(t, int): clean_targets.append({'card': t, 'channel': None})
            else: clean_targets.append(t)

        for target in clean_targets:
            card_id = target['card']
            channel = target.get('channel')

            # AUTO-FIX
            self._ensure_device_active(card_id)
            
            t = threading.Thread(target=self._play_sequence_linux, args=(intro, body, card_id, channel, start_time))
            threads.append(t)
            t.start()
            time.sleep(0.05) 
        
        for t in threads:
            t.join()

    def _play_sequence_linux(self, intro, body, card_id, channel=None, start_time=0):
        """Plays Intro (Optional) -> Body on specific ALSA card + Channel remix"""
        
        # Check for SoX
        has_sox = False
        try:
            subprocess.run(['which', 'play'], stdout=subprocess.DEVNULL, check=True)
            has_sox = True
        except: pass

        device = f"plughw:{card_id},0"
        
        try:
            if has_sox:
                env = os.environ.copy()
                env["AUDIODEV"] = device
                
                # Channel REMIX logic
                # remix 1 0 = Left Only (Channel 1)
                # remix 0 1 = Right Only (Channel 2)
                # remix 1 1 = Mono to Both
                # Default (No flag) = Stereo
                remix_flags = []
                if channel == "left": remix_flags = ['remix', '1', '0']
                elif channel == "right": remix_flags = ['remix', '0', '1']

                print(f"[AudioService] SoX Play {device} (Ch: {channel or 'Stereo'})")
                
                # 1. Intro
                if intro:
                    cmd = ['play', '-v', '0.9', intro] + remix_flags
                    p = subprocess.Popen(cmd, env=env)
                    self._track_process(p)
                    p.wait()
                    self._untrack_process(p)
                
                # 2. Body
                if body:
                    cmd = ['play', '-v', '0.9', body]
                    if start_time > 0: cmd.extend(['trim', str(start_time)])
                    cmd = cmd + remix_flags
                    
                    p = subprocess.Popen(cmd, env=env)
                    self._track_process(p)
                    p.wait()
                    self._untrack_process(p)
            else:
                # Fallback Aplay (No Remix support)
                print(f"[AudioService] Aplay Fallback (No Channel Split) on {device}")
                if intro: subprocess.run(['aplay', '-D', device, intro], check=True)
                if body: subprocess.run(['aplay', '-D', device, body], check=True)
            
        except Exception as e:
            print(f"[AudioService] Playback Error {card_id}: {e}")

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
        """Initializes persistent play pipes for low-latency streaming on ALL target zones"""
        self.stop_streaming() # Stop existing
        targets = self._get_target_cards(zones)
        if not targets: return
        
        print(f"[AudioService] Starting Stream Pipes on: {targets}")
        
        with self.stream_lock:
            self.stream_processes = []
            
            clean_targets = []
            for t in targets:
                if isinstance(t, int): clean_targets.append({'card': t, 'channel': None})
                else: clean_targets.append(t)

            for target in clean_targets:
                 card_id = target['card']
                 channel = target.get('channel')

                 self._ensure_device_active(card_id) 
                 time.sleep(0.05) 
                 device = f"plughw:{card_id},0"
                 
                 # Remix Logic for Stream
                 remix_flags = []
                 if channel == "left": remix_flags = ['remix', '1', '0']
                 elif channel == "right": remix_flags = ['remix', '0', '1']

                 try:
                    print(f"  -> Opening Pipe for {device} (Ch: {channel})")
                    env = os.environ.copy()
                    env["AUDIODEV"] = device
                    
                    cmd = ['play', '-q', '-v', '0.9', '-t', 'raw', '-r', '16000', '-e', 'signed-integer', '-b', '16', '-c', '1', '-']
                    cmd = cmd + remix_flags
                    
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        env=env
                    )
                    self.stream_processes.append(proc)
                 except Exception as e:
                    print(f"  -> Failed to open pipe for {device}: {e}")

    def feed_stream(self, pcm_data):
        """Feeds raw PCM bytes into ALL open audio pipes"""
        with self.stream_lock:
             if self.stream_processes:
                 dead_procs = []
                 for i, proc in enumerate(self.stream_processes):
                     try:
                         if proc.stdin:
                             proc.stdin.write(pcm_data)
                             proc.stdin.flush()
                     except Exception as e:
                         # Broken pipe?
                         dead_procs.append(proc)
                 
                 # Cleanup dead pipes silently
                 for p in dead_procs:
                     if p in self.stream_processes:
                         self.stream_processes.remove(p)

    def stop_streaming(self):
        """Closes all streaming pipes"""
        with self.stream_lock:
            # Close Multi-proc list
            if self.stream_processes:
                 print(f"[AudioService] Closing {len(self.stream_processes)} Stream Pipes")
                 for proc in self.stream_processes:
                     try:
                         proc.stdin.close()
                         proc.terminate()
                     except: pass
                 self.stream_processes = []
            
            # Legacy cleanup
            if self.stream_process:
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

    def play_chime_sync(self, zones):
        """Plays the intro chime on specified zones. Blocks until finished."""
        targets = self._get_target_cards(zones)
        intro_path = self.system_sounds_dir / "intro.mp3"
        
        if not intro_path.exists(): return

        threads = []
        for t_obj in targets:
            card_id = t_obj['card'] if isinstance(t_obj, dict) else t_obj
            channel = t_obj.get('channel') if isinstance(t_obj, dict) else None

            def play_on_card(cid, ch):
                device = f"plughw:{cid},0"
                try:
                    env = os.environ.copy()
                    env["AUDIODEV"] = device
                    
                    remix_flags = []
                    if ch == "left": remix_flags = ['remix', '1', '0']
                    elif ch == "right": remix_flags = ['remix', '0', '1']

                    cmd = ['play', '-q', '-v', '0.9', str(intro_path)] + remix_flags
                    subprocess.run(cmd, env=env, stderr=subprocess.DEVNULL)
                except:
                    pass

            t = threading.Thread(target=play_on_card, args=(card_id, channel))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

    def play_siren(self, zones=None, volume=0.01):
        """Plays a synthetic emergency siren on specified zones (Pi Speakers)"""
        with self._lock:
            if self._siren_active:
                return # Already playing
            self._siren_active = True
            self._siren_stop_event.clear()
            self._siren_volume = volume
        
        targets = self._get_target_cards(zones)
        print(f"[AudioService] Starting Emergency Siren on: {targets}")
        
        def run_siren():
            while not self._siren_stop_event.is_set():
                threads = []
                for t_obj in targets:
                    card_id = t_obj['card'] if isinstance(t_obj, dict) else t_obj
                    channel = t_obj.get('channel') if isinstance(t_obj, dict) else None

                    def play_on_card(cid, ch):
                        device = f"plughw:{cid},0"
                        env = os.environ.copy()
                        env["AUDIODEV"] = device
                        try:
                            remix_flags = []
                            if ch == "left": remix_flags = ['remix', '1', '0']
                            elif ch == "right": remix_flags = ['remix', '0', '1']

                            vol = self._siren_volume
                            cmd = ['play', '-q', '-v', str(vol), '-n', 'synth', '1', 'sine', '600:1200'] + remix_flags
                            
                            p = subprocess.Popen(cmd, env=env, stderr=subprocess.DEVNULL)
                            self._track_process(p)
                            p.wait()
                            self._untrack_process(p)
                        except: pass

                    t = threading.Thread(target=play_on_card, args=(card_id, channel))
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
        targets = self._get_target_cards(zones)
        
        # Run in a separate thread to avoid blocking the Controller
        def daemon_play():
            self._play_multizone(None, file_path, targets, start_time=start_time)
            
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
