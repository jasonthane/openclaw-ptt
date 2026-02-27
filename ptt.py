#!/usr/bin/env python3
"""
openclaw-ptt — Push-to-Talk daemon for OpenClaw (Linux)

Hold a configurable key → records from mic → transcribes locally with
faster-whisper (no API key needed) → sends text to `openclaw agent`.

Audio feedback:
  Key down  → chirp sound (optional)
  Sent      → beep sound (optional)

Set SOUND_PTT_START / SOUND_PTT_SENT to paths of .mp3 files, or leave
empty strings to skip audio feedback.

Usage:
  Configure the ── Config ── section below, then run as root or as a
  user in the `input` and `audio` groups. See README.md for full setup.
"""

import subprocess
import tempfile
import os
import sys
import threading
from pathlib import Path

try:
    import evdev
    from evdev import InputDevice, ecodes
except ImportError:
    print("evdev not found — run: pip install evdev")
    sys.exit(1)

try:
    from faster_whisper import WhisperModel
except ImportError:
    print("faster-whisper not found — run: pip install faster-whisper")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
# Keyboard device path — find yours with: ls /dev/input/by-id/
# Use a by-id path for stability across reboots.
KEYBOARD_DEVICE = "/dev/input/by-id/usb-Logitech_USB_Keyboard-event-kbd"

# ALSA mic device — find yours with: arecord -l
# Format: plughw:<card>,<device>
MIC_CARD = "plughw:3,0"

# Key to hold for push-to-talk (evdev keycode)
# Common choices: KEY_RIGHTALT, KEY_SCROLLLOCK, KEY_F13, KEY_CAPSLOCK
PTT_KEY = ecodes.KEY_RIGHTALT

# Whisper model size: tiny.en, base.en, small.en, medium.en
# tiny.en is fast and works great for voice commands
WHISPER_MODEL = "tiny.en"

# Path to the openclaw binary
# Find yours with: which openclaw
# Or if using nvm: /home/<user>/.nvm/versions/node/<version>/bin/openclaw
OPENCLAW_BIN = "/usr/local/bin/openclaw"

# Optional: paths to .mp3 sound files for audio feedback
# Set to "" to disable
SOUND_PTT_START = ""   # played on key-down (e.g. a chirp/beep)
SOUND_PTT_SENT  = ""   # played when transcription is sent

# ALSA playback device for sound effects (only used if sounds configured)
SOUND_PLAYBACK_DEVICE = "plughw:0,0"
# ─────────────────────────────────────────────────────────────────────────────


def play(path: str):
    """Fire-and-forget audio playback via mpg123."""
    if not path:
        return
    subprocess.Popen(
        ["mpg123", "-q", "-a", SOUND_PLAYBACK_DEVICE, path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


print(f"Loading Whisper model '{WHISPER_MODEL}'...", flush=True)
model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
print("✓ Model ready", flush=True)

recording_proc = None
recording_file = None
is_recording   = False


def start_recording():
    global recording_proc, recording_file, is_recording
    play(SOUND_PTT_START)
    recording_file = tempfile.mktemp(suffix=".wav")
    recording_proc = subprocess.Popen(
        ["arecord", "-D", MIC_CARD, "-f", "S16_LE", "-r", "16000", "-c", "1", recording_file],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    is_recording = True
    print("\r🎤 Recording…     ", end="", flush=True)


def stop_and_transcribe():
    global recording_proc, recording_file, is_recording
    if not is_recording:
        return
    is_recording = False

    recording_proc.terminate()
    recording_proc.wait()

    print("\r⚙  Transcribing…  ", end="", flush=True)
    segments, _ = model.transcribe(recording_file, language="en")
    text = " ".join(s.text.strip() for s in segments).strip()
    os.unlink(recording_file)

    if not text:
        print("\r(silence — nothing sent)         ", flush=True)
        return

    play(SOUND_PTT_SENT)
    print(f"\r📤 You: {text}", flush=True)

    def run_agent():
        result = subprocess.run(
            [OPENCLAW_BIN, "agent", "--agent", "main", "--message", text],
            capture_output=True,
            text=True,
        )
        reply = result.stdout.strip()
        if reply:
            print(f"💬 Agent: {reply}", flush=True)
        if result.returncode != 0:
            print(f"⚠  agent error: {result.stderr.strip()[:120]}", flush=True)

    threading.Thread(target=run_agent, daemon=True).start()


def main():
    try:
        kbd = InputDevice(KEYBOARD_DEVICE)
    except (FileNotFoundError, PermissionError) as e:
        print(f"Cannot open keyboard {KEYBOARD_DEVICE}: {e}")
        print("Try: sudo usermod -aG input $USER  (then log out and back in)")
        sys.exit(1)

    print(f"✓ Listening on {kbd.name}", flush=True)
    print(f"  Hold [{PTT_KEY}] to talk — Ctrl+C to quit.\n", flush=True)

    try:
        for event in kbd.read_loop():
            if event.type == ecodes.EV_KEY and event.code == PTT_KEY:
                if event.value == 1 and not is_recording:    # key down
                    start_recording()
                elif event.value == 0 and is_recording:      # key up
                    stop_and_transcribe()
    except KeyboardInterrupt:
        if is_recording:
            recording_proc.terminate()
        print("\nPTT daemon stopped.")


if __name__ == "__main__":
    main()
