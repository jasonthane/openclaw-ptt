# openclaw-ptt

Push-to-talk daemon for [OpenClaw](https://github.com/openclaw/openclaw) on Linux.

Hold a key → records audio → transcribes locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) → sends to your OpenClaw agent via `openclaw agent`.

**No cloud API needed.** Everything runs locally: `faster-whisper` (tiny.en) transcribes on CPU in a second or two. Private by design.

---

## Requirements

- Linux (tested on Ubuntu 24.04 / 25.10)
- Python 3.8+
- `arecord` (from `alsa-utils`)
- `mpg123` (optional — for audio feedback chirp/beep)
- [OpenClaw](https://github.com/openclaw/openclaw) installed and gateway running

---

## Setup

### 1. Install system dependencies

```bash
sudo apt install alsa-utils mpg123
```

### 2. Create Python venv and install packages

```bash
python3 -m venv ~/ptt-env
source ~/ptt-env/bin/activate
pip install -r requirements.txt
```

### 3. Add user to input and audio groups

```bash
sudo usermod -aG input,audio $USER
# Log out and back in for group changes to take effect
```

### 4. Find your devices

**Keyboard:**
```bash
ls /dev/input/by-id/
```
Pick the `*-event-kbd` path for your keyboard.

**Mic:**
```bash
arecord -l
```
Note the card/device number (e.g. card 3, device 0 → `plughw:3,0`).

**OpenClaw binary:**
```bash
which openclaw
# or if using nvm:
ls ~/.nvm/versions/node/*/bin/openclaw
```

### 5. Configure ptt.py

Edit the `── Config ──` section at the top of `ptt.py`:

```python
KEYBOARD_DEVICE = "/dev/input/by-id/your-keyboard-event-kbd"
MIC_CARD        = "plughw:3,0"          # from arecord -l
PTT_KEY         = ecodes.KEY_RIGHTALT   # key to hold
OPENCLAW_BIN    = "/path/to/openclaw"
SOUND_PTT_START = ""  # optional: path to .mp3 chirp on key-down
SOUND_PTT_SENT  = ""  # optional: path to .mp3 beep when sent
```

**Common PTT key choices:**
| Key | evdev constant |
|-----|---------------|
| Right Alt | `ecodes.KEY_RIGHTALT` |
| Scroll Lock | `ecodes.KEY_SCROLLLOCK` |
| F13 | `ecodes.KEY_F13` |

### 6. Test manually

```bash
source ~/ptt-env/bin/activate
python3 ptt.py
```

Hold your PTT key, speak, release. You should see transcription and a reply from your agent.

### 7. Install as a systemd service

```bash
# Copy ptt.py to your home directory
cp ptt.py ~/ptt.py

# Edit the service file — replace <user> with your username and <uid> with your UID
sed -i "s/<user>/$USER/g; s/<uid>/$(id -u)/g" openclaw-ptt.service

# Install and enable
sudo cp openclaw-ptt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-ptt
```

**Check status:**
```bash
sudo systemctl status openclaw-ptt
journalctl -u openclaw-ptt -f
```

---

## How It Works

```
[Key down] → chirp sound → arecord starts
[Key up]   → arecord stops → faster-whisper transcribes
           → beep sound → openclaw agent --agent main --message "<text>"
           → response printed to stdout / journal
```

The `openclaw agent` command sends the transcription to your running OpenClaw gateway. The response flows back through the WebSocket to the TUI — no external channel (Telegram/Slack) required.

---

## Troubleshooting

**Cannot open keyboard device:**
- Check the path in `KEYBOARD_DEVICE` matches `ls /dev/input/by-id/`
- Verify user is in `input` group: `groups $USER`
- As a system service, `SupplementaryGroups=input audio` must be set (requires system service, not user service)

**Sound effects stop working after reboot (PTT still works):**
- Most likely cause: `XDG_RUNTIME_DIR` not set in the service, so `mpg123` can't reach PipeWire/PulseAudio
- Fix: ensure `Environment=XDG_RUNTIME_DIR=/run/user/<uid>` is in the service file (see template)
- Also note: Ubuntu 25.10+ does not have an `audio` group — remove it from `SupplementaryGroups` if present

**No audio / silence returned:**
- Check mic with: `arecord -D plughw:X,Y -f S16_LE -r 16000 -c 1 test.wav`
- Verify `MIC_CARD` matches your device from `arecord -l`

**openclaw agent fails:**
- Ensure OpenClaw gateway is running: `openclaw gateway status`
- Check `OPENCLAW_BIN` path is correct
- Do **not** use `--deliver` flag if your agent has no external channels configured

---

## Notes

- Whisper `tiny.en` model (~75MB) downloads automatically on first run
- CPU inference with `int8` is fast enough for voice command latency
- The service must be a **system service** (not user service) to use `SupplementaryGroups`

---

*Built for the [OpenClaw](https://github.com/openclaw/openclaw) bridge crew. First deployed on Commander Data, USS Enterprise.*
