import os
import platform
import subprocess
import sys
import zipfile
import tarfile
import shutil
import requests
from pathlib import Path

# --- Configuration ---
PIPER_RELEASE_TAG = "2023.11.14-2"
BASE_URL = f"https://github.com/rhasspy/piper/releases/download/{PIPER_RELEASE_TAG}"

MODELS = {
    "female": {
        "name": "en_US-amy-medium",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx.json"
    },
    "male": {
        "name": "en_US-ryan-medium",
        # Using main for Ryan based on some search results, but v1.0.0 is preferred if it works. 
        # We will try v1.0.0 first for structure consistency.
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/medium/en_US-ryan-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json"
    }
}

DEST_DIR = Path("piper_tts")

def get_system_info():
    system = platform.system()
    machine = platform.machine().lower()
    return system, machine

def download_file(url, dest_path):
    print(f"Downloading {url} to {dest_path}...")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Download complete.")
        return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False

def setup_piper():
    system, machine = get_system_info()
    print(f"Detected System: {system}, Machine: {machine}")

    DEST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Determine Piper Binary URL
    piper_url = ""
    archive_name = ""

    if system == "Windows":
        if "64" in machine:
            archive_name = "piper_windows_amd64.zip"
            piper_url = f"{BASE_URL}/{archive_name}"
        else:
            print("Error: Only Windows x64 is supported by this script for now.")
            return False
    elif system == "Linux":
        if "aarch64" in machine or "arm64" in machine:
            archive_name = "piper_linux_aarch64.tar.gz"
            piper_url = f"{BASE_URL}/{archive_name}"
        elif "x86_64" in machine:
             archive_name = "piper_linux_amd64.tar.gz"
             piper_url = f"{BASE_URL}/{archive_name}"
        else:
            print(f"Warning: Architecture {machine} might not be supported directly. Attempting aarch64 (Pi) default.")
            archive_name = "piper_linux_aarch64.tar.gz"
            piper_url = f"{BASE_URL}/{archive_name}"
    else:
        print(f"Error: Unsupported OS {system}")
        return False

    # 2. Download and Extract Piper
    archive_path = DEST_DIR / archive_name
    executable_path = DEST_DIR / ("piper.exe" if system == "Windows" else "piper")
    
    # Check if already installed
    if not executable_path.exists():
        if download_file(piper_url, archive_path):
            print("Extracting Piper...")
            try:
                if archive_name.endswith(".zip"):
                    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                        # Inspect zip content to see if it has a top-level folder
                        # Usually piper zip has a 'piper/' folder. We want to extract contents directly to DEST_DIR if possible,
                        # or handle the subdirectory.
                        # Let's extract to a temp dir and move.
                        with zipfile.ZipFile(archive_path, 'r') as z:
                            z.extractall(DEST_DIR)
                elif archive_name.endswith(".tar.gz"):
                    with tarfile.open(archive_path, "r:gz") as tar:
                        tar.extractall(DEST_DIR)
                
                print("Extraction complete.")
                # Cleanup archive
                os.remove(archive_path)

                # Adjust structure if needed (Piper zips often extract to a 'piper' subdirectory)
                # If DEST_DIR/piper/piper.exe exists, move contents up or adjust path.
                # However, having it in piper_tts/piper/piper.exe is fine too.
                # Let's standardize: we want executable at DEST_DIR/piper.exe or DEST_DIR/piper/piper.exe
                # We will search for the binary.
                
            except Exception as e:
                print(f"Error extracting: {e}")
                return False
        else:
            print("Failed to download Piper binary.")
            return False
            
    # Ensure Executable Permission (Linux/Mac)
    if system != "Windows" and executable_path.exists():
        try:
            st = os.stat(executable_path)
            os.chmod(executable_path, st.st_mode | 0o111) # Add +x
            print(f"Set execute permissions on {executable_path}")
        except Exception as e:
            print(f"Warning: Failed to set permissions on {executable_path}: {e}")
    else:
        print("Piper binary appears to be already present.")

    # 3. Download Voices
    print("Checking voice models...")
    for voice_type, data in MODELS.items():
        onnx_name = data["name"] + ".onnx"
        json_name = data["name"] + ".onnx.json"
        
        onnx_path = DEST_DIR / onnx_name
        json_path = DEST_DIR / json_name

        if not onnx_path.exists():
            download_file(data["onnx"], onnx_path)
        
        if not json_path.exists():
            download_file(data["json"], json_path)

    print("\nSetup Setup complete!")
    print(f"Piper is located in: {DEST_DIR.absolute()}")
    return True

if __name__ == "__main__":
    success = setup_piper()
    if not success:
        sys.exit(1)
