import os

def create_asoundrc():
    """Creates an ALSA config file to explicitly separate the two USB cards"""
    config_content = """
# Explicitly define two USB Audio Interfaces
# based on the observed 'Device' and 'Device_1' naming

pcm.speaker_one {
    type plug
    slave.pcm "hw:Card=Device"
}

pcm.speaker_two {
    type plug
    slave.pcm "hw:Card=Device_1"
}

# Fallback by index if names fail
pcm.card2 {
    type plug
    slave.pcm "plughw:2,0"
}
pcm.card3 {
    type plug
    slave.pcm "plughw:3,0"
}
"""
    home = os.path.expanduser("~")
    path = os.path.join(home, ".asoundrc")
    print(f"Writing ALSA Config to {path}...")
    with open(path, "w") as f:
        f.write(config_content)
    print("Done. This helps the Pi verify they are separate devices.")

def instruction_max_current():
    print("\n[CRITICAL POWER FIX]")
    print("Your issue (one works, one doesn't) is 90% likely a USB POWER LIMIT.")
    print("The Pi restricts power to USB ports by default.")
    print("\nPLEASE RUN THIS COMMAND IN TERMINAL TO FIX IT:")
    print("sudo sed -i '$ a max_usb_current=1' /boot/config.txt")
    print("sudo sed -i '$ a max_usb_current=1' /boot/firmware/config.txt")
    print("(Then reboot)")

if __name__ == "__main__":
    create_asoundrc()
    instruction_max_current()
