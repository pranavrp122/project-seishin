# Nexus Engine — Bug Fixes & Resolutions

---

## [FIX-01] torchaudio ABI mismatch in seishin-ears

**Symptom**: `OSError: Could not load this library: _torchaudio.abi3.so` when loading Silero VAD via `torch.hub`

**Root cause**: NeMo 26.02 ships NVIDIA's custom PyTorch build (`torch 2.10.0a0+b558c986e8.nv25.11`). Standard `pip install torchaudio` installs `2.11.0` which is compiled against stock PyTorch 2.11 — ABI incompatible.

**Fix**:
- Uninstalled mismatched `torchaudio 2.11.0`
- Installed `onnxruntime 1.24.4` instead
- Loaded Silero VAD ONNX model directly via `onnxruntime.InferenceSession` — no torchaudio dependency
- Copied `silero_vad.onnx` (2.3 MB) to `scripts/` (host-mounted) for persistence

---

## [FIX-02] Mic not accessible inside seishin-ears

**Symptom**: `sounddevice.query_devices()` returned empty list; PortAudio couldn't find any input devices

**Root cause**: Container started without PulseAudio socket mount. WSL2 has no raw ALSA devices (`/dev/snd` only contains `timer`). Audio requires WSLg PulseAudio bridge at `/mnt/wslg/PulseServer`.

**Fix**:
- Stopped and recreated `seishin-ears` with:
  - `-v /mnt/wslg:/mnt/wslg` (WSLg socket)
  - `-e PULSE_SERVER=unix:/mnt/wslg/PulseServer`
- Installed `libportaudio2`, `libpulse0`, `libasound2-plugins` inside container
- Wrote `/etc/asound.conf` to route ALSA default → PulseAudio
- Verified: `pulse` device (32 in/out) visible to sounddevice ✅
- Note: `/run/user/1000/pulse/native` fails with "Access denied" (owned by uid 1000, container runs as root) — use `/mnt/wslg/PulseServer` only

---

## [FIX-03] No real-time feedback while speaking

**Symptom**: Nothing printed to terminal while user spoke into mic; only output after silence gate closed

**Root cause**: Script only printed after VAD flush (end of utterance). No continuous status, no live mic level, no in-progress transcription.

**Fix** (in `nexus_engine.py`):
- Added ASCII mic level bar updated every 32 ms
- Added inline VAD probability display
- Added state labels on overwriting `\r` line: `idle` / `detecting...` / `SPEAKING...` / trailing silence counter
- Added live Parakeet preview every 1.5 s while in SPEAKING state
- Lowered `VAD_SPEECH_THRESH` from `0.5` to `0.3`
- Lowered `VAD_MIN_SPEECH_FRAMES` from `5` to `3`

---

## [FIX-04] Verbose docker exec command required to launch

**Symptom**: User had to type `docker exec -it -e PULSE_SERVER=... seishin-ears python3 ...` every time

**Fix**:
- Created `run.sh` wrapper at `/home/prana/nexus-engine/run.sh`
- Added `alias nexus="bash /home/prana/nexus-engine/run.sh"` to `~/.bashrc`
- Launch command is now: `nexus`

---

## [FIX-05] Noisy NeMo/PyTorch startup warnings

**Symptoms**:
- `FutureWarning: The pynvml package is deprecated`
- `OneLogger: Setting error_handling_strategy...`
- `No exporters were provided`
- `Multiple distributions found for package modelopt`
- `pydub: Couldn't find ffmpeg`
- `[NeMo W ...]` lines during model load

**Fixes**:
| Warning | Resolution |
|---|---|
| `pynvml deprecated` | `pip uninstall pynvml` + `pip install nvidia-ml-py` in container |
| OneLogger / telemetry | `NEMO_TESTING=1` env var in `run.sh` and script |
| `modelopt` distribution warning | `warnings.filterwarnings('ignore')` before NeMo import |
| `pydub / ffmpeg` | `apt install ffmpeg` in container |
| All `[NeMo W]` lines | `logging.disable(logging.WARNING)` before NeMo import, restored after |
| Remaining warnings | `python3 -W ignore` flag in `run.sh` |

---

## [FIX-06] "Tuple indices must be integers" crash in device discovery

**Symptom**: `TypeError: tuple indices must be integers or slices, not str`
Occasionally crashes with `sounddevice.PortAudioError: Error querying device -1`

**Root cause**: The `sounddevice` library can return device payloads as either `list[dict]` or `list[tuple]` depending on ALSA enumeration format. The ALSA query defaulted to -1 when it failed to parse the device list cleanly.

**Fix**:
- Rewrote `_find_input_device()` to use a generic `try/except` iteration loop to scan all returned structs.
- Reinstated the custom device targeting logic to bypass the `device = -1` crash so `sounddevice` flawlessly binds to the available microphone.

---

## [FIX-07] vLLM Read Timeout on first generation

**Symptom**: `HTTPConnectionPool(host='172.17.0.1', port=8001): Read timed out.`

**Root cause**: Our initial `ask_brain()` python request timeout was hardcoded to `10` seconds. On the first LLM pass, vLLM has to fully compile PyTorch execution graphs which can take > 20s.

**Fix**:
- Increased `requests.post` timeout from `10` seconds to `60` seconds in `scripts/nexus_engine.py` to allow for graph compilation on cold-starts.

---

## [FIX-08] Buffer length truncation logic clipping long speeches

**Symptom**: If the user spoke continuously for > 2 seconds, the start of the audio was wiped out.

**Root cause**: A hardcoded `max_buffer_len = int(2.0 * RATE)` was continuously clipping the trailing ends of audio arrays.

**Fix**:
- Removed the max buffer constraint and the automated silence threshold (`1.3`s).
- Implemented a background Python `threading.Event()` on `sys.stdin.readline()` so the user can speak endlessly, and the engine only flushes the buffer to the brain when the `Enter` key is pressed.

---

## [FIX-09] Live transcription only visible in ears daemon terminal

**Symptom**: The `nexus` terminal stayed blank until the final flush. All live transcription feedback (`> what's the most expensive...`) was printed locally in `ears_daemon.py` instead of being routed to `nexus_engine.py`.

**Root cause**: `ears_daemon.py` was printing live ASR text directly via `print(f'\r> {text}')` instead of forwarding it over HTTP to the nexus engine.

**Fix**:
- Stripped all UI `print()` calls from `ears_daemon.py` — it now runs as a silent daemon with minimal status logging (`Parakeet live`, `Silero VAD live`, `[stream] ...`)
- Added `send_stream(text)` function that POSTs `{"text": text}` to `localhost:5050/stream` in a fire-and-forget daemon thread
- Added `/stream` route in `nexus_engine.py` that prints `\r> {text}` with carriage return overwrite
- `/flush` route now prints a newline before the brain response and `Listening...` after completion
- `nexus_engine.py` prints initial `Listening...` on startup
- All terminal UI now lives exclusively in the nexus engine tab
