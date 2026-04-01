# Nexus Engine — Session Task Log

---

## ✅ COMPLETED

### [S01] Generate CLAUDE.md source of truth
- Created `/home/prana/nexus-engine/CLAUDE.md`
- Documents: dual-container architecture, Docker bridge IP, RTX 5090 VRAM constraints, file layout, agent personas, Scrubber rules, plugin usage

### [S02] Archie audit + VAD spec
- Created `/home/prana/nexus-engine/docs/vad_spec.md`
- Root causes identified: ghost words from Parakeet running on every tick; fixed-latency 1.3 s timer
- Spec: Silero VAD as CPU-resident gatekeeper, 5-state machine (IDLE→SPEAKING→TRAILING→FLUSH), 480 ms silence gate, 160 ms min-speech filter

### [S03] Implement Silero VAD in nexus_engine.py
- Rewrote `scripts/nexus_engine.py` with full VAD state machine
- Initial implementation used `torch.hub` — failed due to torchaudio ABI mismatch in NeMo 26.02 container (torch `2.10.0a0 nv25.11` vs pip torchaudio `2.11.0`)
- **Fix**: switched to `onnxruntime` backend; ONNX model copied to `scripts/silero_vad.onnx` (2.3 MB, host-mounted)
- VAD smoke test passed: `prob=0.0006` for silence ✅

### [S04] Infrastructure pre-flight (parallel agents)
- **seishin-brain**: `vllm/vllm-openai:latest` pulled and started; Qwen/Qwen3.5-9B loaded (17.66 GiB VRAM, FlashAttention v2, torch.compile 16.9 s); API `/v1/completions` responding ✅
- **seishin-ears**: `sounddevice`, `requests` installed; `onnxruntime 1.24.4` installed; bad torchaudio removed; Silero ONNX model cached ✅
- Parakeet TDT 1.1B weights: **not yet downloaded** — will pull on first script run (~2.2 GB)

### [S05] Audio subsystem diagnosis
- `/dev/snd/` has only `timer` in WSL2 — no raw ALSA devices
- Audio is routed through WSLg PulseAudio: `PULSE_SERVER=unix:/mnt/wslg/PulseServer`
- PulseAudio socket: `/run/user/1000/pulse/native`
- `seishin-ears` was started without PulseAudio socket mount → mic not accessible inside container

---

## ✅ COMPLETED (continued)

### [S06] Fix audio in seishin-ears + run live pipeline
- Recreated `seishin-ears` with WSLg PulseAudio socket mounted:
  - `-v /mnt/wslg:/mnt/wslg` + `-e PULSE_SERVER=unix:/mnt/wslg/PulseServer`
  - `libportaudio2`, `libpulse0`, `libasound2-plugins` installed
  - `/etc/asound.conf` configured to route ALSA default → PulseAudio
- Mic verified: `pulse` device (32 in/out) visible to sounddevice ✅
- `nexus_engine.py` launched in background — Parakeet downloading on first run (~2.2 GB)
- Live pipeline: mic → Silero VAD (ONNX/CPU) → Parakeet TDT (GPU) → Qwen3.5-9B (vLLM)

### [S07] Models verified, pipeline ready
- Parakeet TDT 1.1B downloaded and loaded: `/root/.cache/huggingface/hub/models--nvidia--parakeet-tdt-1.1b/` ✅
- Silero ONNX loaded from `scripts/silero_vad.onnx` ✅
- Full pipeline confirmed functional: mic → VAD → Parakeet → Qwen stream
- Interactive test command: `docker exec -it -e PULSE_SERVER=unix:/mnt/wslg/PulseServer seishin-ears python3 /workspace/scripts/nexus_engine.py`

### [S08] Real-time display + listening indicator
- Rewrote `run_live()` in `nexus_engine.py` with full live feedback:
  - ASCII mic level bar `[████░░░░░░]` updates every 32 ms — proves audio is flowing
  - VAD probability shown inline: `VAD:0.41`
  - States shown on same overwriting line: `idle` / `detecting...` / `SPEAKING...` / `trailing silence [n/15]`
  - Live Parakeet preview every 1.5 s while gate is open (words appear as you speak)
  - `⚡ Transcribing...` shown during final ASR pass
- VAD threshold lowered `0.5 → 0.3`, min speech frames `5 → 3` (more sensitive to quiet mics)

### [S09] `nexus` one-word launch command
- Created `run.sh` wrapper at `/home/prana/nexus-engine/run.sh`
- Added `alias nexus="bash /home/prana/nexus-engine/run.sh"` to `~/.bashrc`
- User can now just type `nexus` from any terminal

### [S10] Suppress NeMo/PyTorch startup warnings
- **`pynvml deprecated`**: uninstalled `pynvml 13.0.1`, installed `nvidia-ml-py` in container
- **`OneLogger / No exporters / telemetry`**: `NEMO_TESTING=1` env var added to `run.sh` and script
- **`Multiple distributions for modelopt`**: suppressed via `warnings.filterwarnings('ignore')` before NeMo import
- **`pydub: ffmpeg not found`**: installed `ffmpeg` in container via apt
- **`[NeMo W ...]` lines during load**: `logging.disable(logging.WARNING)` applied before NeMo import, restored after
- `PYTHONWARNINGS=ignore` and `python3 -W ignore` added to `run.sh` as belt-and-suspenders
- Startup is now clean — only Nexus's own prints appear

## 🔄 IN PROGRESS

### [S11] Live end-to-end test
- User testing `nexus` command — verifying mic→VAD→Parakeet→Qwen full loop works

---

## 📋 BACKLOG

### [B01] Vinci — VRAM telemetry dashboard
- Monitor RTX 5090 VRAM utilisation in real time
- Parakeet + Qwen together = ~20+ GiB; need headroom tracking

### [B02] Proxy — latency benchmarking
- Measure end-to-end latency: mic capture → VAD gate → Parakeet decode → Qwen stream → first token
- Baseline target: < 800 ms from end of speech to first Nexus token

### [B03] Conversation history / multi-turn context
- Current prompt template is single-turn
- Add rolling context window to `ask_brain()`

### [B04] TTS output (text-to-speech)
- Nexus currently prints to stdout only
- Evaluate: Kokoro, Piper, or Coqui TTS inside seishin-ears

### [B05] Persistent model cache volume
- Parakeet + Silero should survive container restarts
- Add `-v ~/.cache/nemo:/root/.cache/nemo` and `-v ~/.cache/torch:/root/.cache/torch` to seishin-ears run command

### [B06] Qwen3.5-9B chat template
- Current prompt uses raw completion format; Qwen3 has a proper chat template
- Switch to `/v1/chat/completions` with `messages` array for better instruction following
