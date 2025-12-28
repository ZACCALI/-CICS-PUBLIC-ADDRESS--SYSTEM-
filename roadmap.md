# Strategic Cross-Platform Roadmap

## **Phase 1: Feature Perfection (Windows Dev)**
**Goal**: Build the robust logic on your powerful PC first. By sticking to Windows for dev, we move fast.

### 1. **Implement "Human AI Voice" (Piper TTS)**
- **Status**: **[COMPLETE]**
- **Action**: 
    - [x] Download Piper for Windows.
    - [x] Update `audio_service.py` to use `subprocess` to call Piper instead of PowerShell for TTS.
    - **Advantage**: Piper works the *exact same way* on Windows and Linux (command line tool). This makes migration easier than using `System.Speech`.

### 2. **Refactor Audio Service for Linux Compatibility**
- **Status**: **[COMPLETE]**
- **Existing Issue**: Current code uses `PowerShell` (Windows Only).
- **The Fix**: Update `audio_service.py` to detect `platform.system()`.
    - **If Windows**: Use PowerShell (or Piper + VLC).
    - **If Linux (Pi)**: Use `cvlc` (VLC) or `mpv` command line.
- **Action**: Create a "Universal Audio Driver" layer in Python.

## **Phase 2: Cloud Deployment (Frontend)**
- **Action**: Deploy React App to Firebase Hosting.
- **Result**: Mobile control ready.

## **Phase 3: The "Pi 5" Migration**
**Goal**: "Copy-Paste" simplicity.

### 1. **Pi Preparation**
- Install Raspberry Pi OS (64-bit recommended for Pi 5).
- Run Script: `sudo apt install vlc piper-tts python3-pip`.

### 2. **Code Transfer**
- Copy `backend/` folder to Pi.
- Run `pip install -r requirements.txt`. (We will ensure requirements are clean).

### 3. **Validation**
- Run `python3 app.py`.
- Because we did Phase 1 (Universal Driver), it will automatically detect "Linux" and switch to VLC/Piper without crashing.

---

## **Why This Plan Works**
- **Piper TTS** is the key. By using Piper on Windows now, you are effectively testing the *exact same AI engine* the Pi will use.
- **Abstraction**: We hide the messy "how to play sound" details inside `audio_service.py`, so the rest of your system (Scheduler, API) doesn't care if it's Windows or Linux.
