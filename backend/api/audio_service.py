import os
import subprocess
import threading
import platform
import uuid
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AudioService:
    def __init__(self):
        self.current_process = None
        self._lock = threading.Lock()
        
        # Piper Setup
        # Assuming piper_tts is in backend/piper_tts, and this file is in backend/api/
        self.base_dir = Path(__file__).resolve().parent.parent / "piper_tts"
        self.os_type = platform.system()
        self.piper_exe = self._find_piper_executable()
        self.voices = self._scan_voices()
        
        if not self.piper_exe:
            print("[AudioService] Warning: Piper TTS not found. Using System Fallback.")

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
            if p.exists():
                return str(p)
                
        # Recursive fallback
        for path in self.base_dir.rglob(exe_name):
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
            
            # Allow clean cleanup of old files? 
            # For now, we generate new ones. Ideally we need a cleanup job.
            
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

    def play_text(self, text: str, voice: str = "female"):
        """Plays text using Piper (or Windows Fallback)"""
        self.stop()
        print(f"[AudioService] Speaking: {text} (Voice: {voice})")
        
        # 1. Try Piper
        wav_path = self._generate_piper_audio(text, voice)
        
        if wav_path:
            # Play generated WAV
            self.play_file(wav_path)
            return

        # 2. Fallback to Windows TTS
        safe_text = text.replace("'", "''")
        command = [
            'powershell', 
            '-Command', 
            f"Add-Type –AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe_text}')"
        ]
        self._run_command(command)

    def play_intro(self, file_path: str):
        """Plays the intro chime synchronously"""
        self.stop()
        print(f"[AudioService] Playing Intro: {file_path}")
        
        if not os.path.exists(file_path):
            fallback_script = "[console]::beep(800, 400); Start-Sleep -Milliseconds 100; [console]::beep(600, 600)"
            self._run_command(['powershell', '-c', fallback_script])
            return

        safe_path = file_path.replace("'", "''")
        ps_script = f"""
        Add-Type -AssemblyName PresentationCore, PresentationFramework;
        $p = New-Object System.Windows.Media.MediaPlayer;
        $p.Open('{safe_path}');
        $attempts = 20; 
        while (-not $p.NaturalDuration.HasTimeSpan -and $attempts -gt 0) {{ Start-Sleep -Milliseconds 100; $attempts--; }}
        $p.Play();
        if ($p.NaturalDuration.HasTimeSpan) {{
            while ($p.Position -lt $p.NaturalDuration.TimeSpan) {{ Start-Sleep -Milliseconds 100; }}
        }} else {{ Start-Sleep -Seconds 4; }}
        $p.Close();
        """
        try:
            subprocess.run(['powershell', '-c', ps_script], check=True)
        except Exception as e:
            print(f"[AudioService] Intro playback failed: {e}")

    def play_file(self, file_path: str):
        """Plays audio file using PowerShell"""
        self.stop() 
        safe_path = file_path.replace("'", "''")
        
        if file_path.lower().endswith('.wav'):
             command = ['powershell', '-c', f"(New-Object Media.SoundPlayer '{safe_path}').PlaySync()"]
        else:
             ps_script = f"""
                Add-Type -AssemblyName PresentationCore, PresentationFramework;
                $p = New-Object System.Windows.Media.MediaPlayer;
                $p.Open('{safe_path}');
                $attempts = 20; 
                while (-not $p.NaturalDuration.HasTimeSpan -and $attempts -gt 0) {{ Start-Sleep -Milliseconds 100; $attempts--; }}
                $p.Play();
                if ($p.NaturalDuration.HasTimeSpan) {{
                    while ($p.Position -lt $p.NaturalDuration.TimeSpan) {{ Start-Sleep -Milliseconds 500 }}
                }} else {{ Start-Sleep -Seconds 10; }}
                $p.Close();
             """
             command = ['powershell', '-c', ps_script]
        
        self._run_command(command)

    def stop(self):
        """Stops the currently running audio process"""
        with self._lock:
            if self.current_process:
                print("[AudioService] Stopping Audio...")
                try:
                    self.current_process.terminate()
                except:
                    pass
                self.current_process = None

    def _run_command(self, command):
        def target():
            proc = None
            with self._lock:
                try:
                    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.current_process = proc
                except Exception as e:
                    print(f"[AudioService] Exception starting process: {e}")
                    return

            if proc:
                try:
                    stdout, stderr = proc.communicate()
                    if stderr: print(f"[AudioService] Process Error: {stderr}")
                except: pass
                finally:
                    with self._lock:
                        if self.current_process == proc: self.current_process = None

        thread = threading.Thread(target=target)
        thread.start()

    def play_announcement(self, intro_path: str, text: str, voice: str = "female"):
        """Plays Intro Chime followed by Piper TTS"""
        self.stop()
        print(f"[AudioService] Announcing: Intro -> '{text}' (Voice: {voice})")

        # 1. Generate Piper Audio FIRST (Blocking, but fast-ish)
        wav_path = self._generate_piper_audio(text, voice)
        
        # 2. Construct Script
        safe_intro = intro_path.replace("'", "''")
        
        if wav_path:
            safe_wav = wav_path.replace("'", "''")
            # Play Intro (MediaPlayer) -> Play Wav (SoundPlayer)
            ps_script = f"""
            Add-Type -AssemblyName PresentationCore, PresentationFramework;
            
            # 1. Play Intro
            $p = New-Object System.Windows.Media.MediaPlayer;
            $p.Open('{safe_intro}');
            $attempts = 20; 
            while (-not $p.NaturalDuration.HasTimeSpan -and $attempts -gt 0) {{ Start-Sleep -Milliseconds 100; $attempts--; }}
            $p.Play();
            if ($p.NaturalDuration.HasTimeSpan) {{
                while ($p.Position -lt $p.NaturalDuration.TimeSpan) {{ Start-Sleep -Milliseconds 100; }}
            }} else {{ Start-Sleep -Seconds 4; }}
            $p.Close();
            
            # 2. Play TTS Wav
            (New-Object Media.SoundPlayer '{safe_wav}').PlaySync();
            """
        else:
            # Fallback to System TTS
            safe_text = text.replace("'", "''")
            ps_script = f"""
            Add-Type -AssemblyName PresentationCore, PresentationFramework;
            Add-Type -AssemblyName System.Speech;
            
            $p = New-Object System.Windows.Media.MediaPlayer;
            $p.Open('{safe_intro}');
            $attempts = 20;
            while (-not $p.NaturalDuration.HasTimeSpan -and $attempts -gt 0) {{ Start-Sleep -Milliseconds 100; $attempts--; }}
            $p.Play();
            if ($p.NaturalDuration.HasTimeSpan) {{
                while ($p.Position -lt $p.NaturalDuration.TimeSpan) {{ Start-Sleep -Milliseconds 100; }}
            }} else {{ Start-Sleep -Seconds 4; }}
            $p.Close();
            
            # Fallback TTS
            $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer;
            $synth.Speak('{safe_text}');
            """

        self._run_command(['powershell', '-c', ps_script])

    def play_intro_async(self, file_path: str):
         """Plays intro asynchronously"""
         self.stop()
         safe_path = file_path.replace("'", "''")
         ps_script = f"""
         Add-Type -AssemblyName PresentationCore, PresentationFramework;
         $p = New-Object System.Windows.Media.MediaPlayer;
         $p.Open('{safe_path}');
         $attempts = 20; 
         while (-not $p.NaturalDuration.HasTimeSpan -and $attempts -gt 0) {{ Start-Sleep -Milliseconds 100; $attempts--; }}
         $p.Play();
         if ($p.NaturalDuration.HasTimeSpan) {{
            while ($p.Position -lt $p.NaturalDuration.TimeSpan) {{ Start-Sleep -Milliseconds 100; }}
         }} else {{ Start-Sleep -Seconds 4; }}
         $p.Close();
         """
         self._run_command(['powershell', '-c', ps_script])

audio_service = AudioService()
