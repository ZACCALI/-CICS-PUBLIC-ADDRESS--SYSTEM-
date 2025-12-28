import os
import subprocess
import platform
import logging
from pathlib import Path
import tempfile
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AudioService:
    def __init__(self, base_dir=None):
        if base_dir is None:
            # Default to 'piper_tts' in the same directory as this script
            self.base_dir = Path(__file__).parent / "piper_tts"
        else:
            self.base_dir = Path(base_dir)

        self.os_type = platform.system()
        self.piper_exe = self._find_piper_executable()
        self.voices = self._scan_voices()
        
        if not self.piper_exe:
            logger.warning("Piper executable not found. Will use fallback TTS.")
        else:
            logger.info(f"Piper found at: {self.piper_exe}")

    def _find_piper_executable(self):
        """Finds the piper executable within the base directory."""
        exe_name = "piper.exe" if self.os_type == "Windows" else "piper"
        
        # Check direct path (piper_tts/piper.exe)
        direct_path = self.base_dir / exe_name
        if direct_path.exists():
            return str(direct_path)
            
        # Check subfolder (piper_tts/piper/piper.exe) - common in releases
        subfolder_path = self.base_dir / "piper" / exe_name
        if subfolder_path.exists():
            return str(subfolder_path)
            
        # Search recursively
        for path in self.base_dir.rglob(exe_name):
            return str(path)
            
        return None

    def _scan_voices(self):
        """Scans for available .onnx voice models."""
        voices = {}
        if not self.base_dir.exists():
            return voices

        for onnx_file in self.base_dir.rglob("*.onnx"):
            # Map simple names to full paths
            # e.g., 'en_US-lessac-medium' -> path
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

    def speak(self, text, voice_key="female", output_file="output.wav"):
        """
        Generates audio from text and plays it.
        
        Args:
            text (str): The text to speak.
            voice_key (str): Key for the voice ('female', 'male', or full model name).
            output_file (str): Path to save the generated wav file.
        """
        if not text:
            return

        if self.piper_exe and (voice_key in self.voices):
             # Try Piper
             model_path = self.voices[voice_key]
             logger.info(f"Using Piper voice: {voice_key} ({Path(model_path).name})")
             
             try:
                 self._generate_audio_piper(text, model_path, output_file)
                 self._play_audio(output_file)
                 return
             except Exception as e:
                 logger.error(f"Piper TTS failed: {e}")
                 logger.info("Falling back to system TTS.")
        
        # Fallback
        self._fallback_tts(text)

    def _generate_audio_piper(self, text, model_path, output_file):
        """Calls Piper binary to generate audio."""
        cmd = [
            self.piper_exe,
            "--model", model_path,
            "--output_file", output_file
        ]
        
        # Piper expects text via stdin
        process = subprocess.Popen(
            cmd, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(input=text)
        
        if process.returncode != 0:
            raise RuntimeError(f"Piper process failed with code {process.returncode}: {stderr}")

    def _play_audio(self, file_path):
        """Plays the audio file using platform-specific tools."""
        abs_path = os.path.abspath(file_path)
        
        if self.os_type == "Windows":
            # Use PowerShell to play wav
            ps_cmd = f'(New-Object Media.SoundPlayer "{abs_path}").PlaySync()'
            subprocess.run(["powershell", "-c", ps_cmd], check=True)
            
        elif self.os_type == "Linux":
            # Try aplay (ALSA) or paplay (PulseAudio)
            try:
                subprocess.run(["aplay", abs_path], check=True)
            except (FileNotFoundError, subprocess.CalledProcessError):
                try:
                    subprocess.run(["paplay", abs_path], check=True)
                except (FileNotFoundError, subprocess.CalledProcessError):
                    logger.error("No suitable audio player found (tried aplay, paplay).")

    def _fallback_tts(self, text):
        """Uses system default TTS."""
        logger.info(f"Fallback TTS: {text}")
        
        if self.os_type == "Windows":
            # PowerShell System.Speech
            # Escape quotes in text
            safe_text = text.replace('"', '\\"')
            ps_code = f"""
            Add-Type -AssemblyName System.Speech;
            $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer;
            $synth.Speak("{safe_text}");
            """
            subprocess.run(["powershell", "-c", ps_code], check=True)
            
        elif self.os_type == "Linux":
            # Try espeak if available
            try:
                subprocess.run(["espeak", text], check=True)
            except FileNotFoundError:
                logger.error("espeak not installed. Cannot speak.")

# Example usage if run directly
if __name__ == "__main__":
    service = AudioService()
    print("Testing Female Voice...")
    service.speak("Hello, this is the offline Piper Text to Speech service.", "female")
    
    print("Testing Male Voice...")
    service.speak("This is the male voice option.", "male")
