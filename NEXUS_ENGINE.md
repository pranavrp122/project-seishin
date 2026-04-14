# Nexus Engine — Project-Specific Details

**Note**: This document contains Nexus Engine-specific architecture, configuration, and constraints. For general Claude Code standards and workflow, see `CLAUDE.md`.

---

## System Architecture

Nexus Engine is a zero-latency, voice-driven conversational AI using a client-daemon architecture for instant dev iteration. The system spans three Docker containers with HTTP bridges between ears, nexus engine, and mouth daemons.

```
[ Mic (host PulseAudio via WSLg) ]
        │
[ ears_daemon.py ] ─── Silero VAD (CPU) + Parakeet TDT 0.6B v2 (GPU)
        │  HTTP POST to localhost:5050
        │  /prefill (fire-and-forget during speech)
        │  /flush   (blocking, after silence detected)
        │  On IDLE→SPEAKING: POST /stop to mouth + nexus (interrupt)
        │
[ nexus_engine.py ] ─── Lightweight HTTP server (port 5050, zero ML models)
        │  HTTP POST (streaming) to vLLM
        │  Sentence buffer → POST /speak to mouth daemon (per sentence)
        │
[ seishin-brain ] ──── LLM inference (vLLM serving Qwen/Qwen3.5-9B FP8)
        │
[ mouth_daemon.py ] ─── Qwen3-TTS 1.7B BF16 (GPU) → resample 48kHz → Bluetooth headphones
        │  HTTP server (port 5051)
        │  /speak (text → TTS queue → streaming audio)
        │  /stop  (interrupt: drain queues, stop playback)
```

Both `ears_daemon.py` and `nexus_engine.py` run inside `seishin-ears`. The daemon loads heavy models once and stays running. The engine can be restarted in ~0.1s to iterate on prompts, history logic, or generation params without reloading models. `mouth_daemon.py` runs inside `seishin-mouth`.

## Pipeline Flow

1. `ears_daemon.py` captures mic audio at 16kHz via `sounddevice.InputStream`
2. Silero VAD (CPU) classifies 512-sample chunks as speech/silence
3. VAD state machine: IDLE → SPEAKING → TRAILING → FLUSH
4. During SPEAKING/TRAILING, Parakeet 0.6B v2 runs live transcription and sends it via `POST /stream` to nexus engine
5. Every 4 new words, ears daemon sends `POST /prefill` to warm vLLM's KV cache
6. On FLUSH (480ms silence), ears daemon sends `POST /flush` to nexus engine
7. `nexus_engine.py` displays live transcription via `/stream`, receives flush, calls `ask_brain()` which streams the Qwen response to stdout
8. During streaming, sentence buffer detects complete sentences and POSTs each to `mouth_daemon.py` via `/speak`
9. `mouth_daemon.py` parses `(emotion)` prefix from text, synthesizes speech via Qwen3-TTS with emotion-aware `instruct` parameter, resamples to 48kHz, plays through PulseAudio to Bluetooth headphones
10. When user starts speaking again (IDLE→SPEAKING), ears daemon fires `/stop` to both mouth and nexus to interrupt playback and cancel generation
11. Nexus engine manages conversation history, response quality filtering, and TTFT counters

## Docker Containers

| Container | Image | Port | Role |
|---|---|---|---|
| `seishin-brain` | `vllm/vllm-openai:latest` | `8001` | LLM inference (Qwen3.5-9B FP8) |
| `seishin-ears` | `nvcr.io/nvidia/nemo:26.02` | — | ASR pipeline (ears + nexus) |
| `seishin-mouth` | `pytorch/pytorch:2.11.0-cuda13.0-cudnn9-runtime` | `5051` | TTS playback (Qwen3-TTS 1.7B BF16) |

- Bridge IP for inter-container communication: `172.17.0.1`
- `seishin-ears` mounts `~/nexus-engine/scripts` → `/workspace/scripts`
- `seishin-ears` runs with `--privileged` flag for audio device access
- `seishin-ears` requires PulseAudio socket: `-v /mnt/wslg:/mnt/wslg -e PULSE_SERVER=unix:/mnt/wslg/PulseServer`
- `seishin-mouth` mounts `~/nexus-engine/scripts` → `/workspace/scripts` and `~/.cache/huggingface` for model weights
- `seishin-mouth` requires PulseAudio socket (same as ears) for Bluetooth audio output

## Hardware Constraints (RTX 5090)

- GPU: NVIDIA RTX 5090, 32 GB VRAM
- Three GPU models with strict VRAM limits:

| Model | Container | Precision | VRAM Cap Mechanism | VRAM Budget |
|---|---|---|---|---|
| Qwen3.5-9B | seishin-brain | FP8 (`--quantization fp8`) | `--gpu-memory-utilization 0.55` | ~20.3 GB |
| Parakeet TDT 0.6B v2 | seishin-ears | FP16 (CPU→FP16→CUDA) | `torch.cuda.set_per_process_memory_fraction(0.12)` | ~3.9 GB cap (~3.1 GB actual) |
| Qwen3-TTS 1.7B | seishin-mouth | BF16 | `torch.cuda.set_per_process_memory_fraction(0.18)` | ~5.9 GB cap (~4.3 GB actual) |
| **Total** | | | | **~27.7 GB actual / 32 GB** |

- FP8 quantization halves Qwen3.5-9B model weights from ~18 GB to ~10.8 GB (natively supported on Blackwell)
- `PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512` (mouth) / `256` (ears) prevents memory fragmentation
- Never load additional large models without profiling VRAM headroom first

## Key Files

| Path | Purpose |
|---|---|
| `scripts/ears_daemon.py` | Heavy daemon: Mic → Silero VAD → Parakeet TDT 0.6B v2 ASR → HTTP to nexus engine; fires /stop on interrupt |
| `scripts/nexus_engine.py` | Lightweight engine: HTTP server (port 5050) → conversation history → vLLM → sentence buffer → mouth |
| `scripts/mouth_daemon.py` | TTS daemon: HTTP server (port 5051) → Qwen3-TTS GPU → resample 48kHz → sounddevice → Bluetooth |
| `scripts/system_prompts.py` | System prompt (voice-optimized), seed history, dodge phrases |
| `docs/FIXES.md` | Bug fix log with numbered entries |
| `docs/TASKS.md` | Agent task roadmap |
| `README.md` | Setup guide for collaborators |
| `.env` | Environment config (gitignored) |
| `.gitignore` | Excludes .env, __pycache__/ |

## LLM Endpoint

- URL: `http://172.17.0.1:8001/v1/completions`
- Model: `Qwen/Qwen3.5-9B`
- Streaming: enabled (`stream=True`)
- Stop tokens: `["User:", "\n\n"]`
- Generation params: `temperature=0.7`, `repetition_penalty=1.15`, `max_tokens=300`
- Timeout: 60s (accommodates initial vLLM CUDA graph compilation)
- System prompt enforces "Nexus" persona with anti-repetition, brevity, voice-output rules, and emotion prefix instructions
- LLM emits `(emotion)` prefix (e.g., `(warm)`, `(curious)`) which mouth daemon converts to TTS `instruct` parameter
- Response quality filter drops garbage replies (dodge phrases) to prevent history poisoning
- Sentence buffer in `ask_brain()` forwards complete sentences to mouth daemon via fire-and-forget POST
- `/stop` endpoint cancels streaming generation when user interrupts
- Voice command "nexus clear memory" resets conversation history to seed state without calling brain

## ASR Configuration

- Model: `nvidia/parakeet-tdt-0.6b-v2` loaded via `nemo_asr.models.ASRModel.from_pretrained()`
- Inference: `model.transcribe([buffer], batch_size=1, verbose=False)`
- tqdm progress bar suppressed via `contextlib.redirect_stderr(io.StringIO())`
- Sample rate: 16000 Hz, blocksize: 800
- Silero VAD gatekeeper: 512-sample chunks, speech threshold 0.5, 480ms silence gate
- VAD runs on CPU, Parakeet on GPU — zero contention

## TTS Configuration

- Model: `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` loaded at BF16 on CUDA in `seishin-mouth`
- Speaker: configurable via `TTS_SPEAKER` env var (default: Aiden)
- Emotion: LLM emits `(emotion)` prefix → mouth parses and converts to `instruct="Speak in a {emotion} voice"`
- Inference: Hybrid mode via `qwen3-tts-triton` TritonFasterRunner (CUDA Graph + Triton fused kernels, ~4.7x speedup)
- Streaming: `runner.generate_streaming(chunk_size=4)` yields `(audio_chunk, sample_rate, timing_dict)`
- Audio output: resampled to 48kHz via pre-computed FIR filter (`firwin` + `upfirdn`) for Bluetooth Studio Quality
- Stability: `gc.collect()` + `torch.cuda.empty_cache()` after every generation; periodic runner reload every 5 generations to reset CUDA graph cache
- Playback: `sounddevice.RawOutputStream` blocking writes at 48kHz/mono/int16 → PulseAudio → Bluetooth headphones (no callback — TTS worker writes directly to stream)
- Interrupt: ears IDLE→SPEAKING fires `/stop` to mouth (`stream.abort()` + restart) and nexus (cancels generation)
- Graceful degradation: if mouth container is down, `send_to_mouth()` timeout fires silently — no impact on text output

## Client-Daemon Architecture

- `ears_daemon.py` loads Parakeet + Silero once, stays running indefinitely
- `nexus_engine.py` is a zero-model HTTP server that restarts in ~0.1s
- Communication: `localhost:5050` — `/stream` (live text), `/prefill` (fire-and-forget), and `/flush` (blocking)
- Workflow: start ears daemon once, restart nexus engine freely to iterate on prompts/logic
- Both scripts run inside `seishin-ears` container (scripts are live-mounted)

## Known Issues & Fixes

- **Run Scripts Dependency**: When updating `run_shortcuts/run_ears.sh` or `run_shortcuts/run_brain.sh`, you MUST also update `run_shortcuts/run.sh` to ensure consistency.
- **Live Transcription Routing**: RESOLVED — `ears_daemon.py` now sends live transcriptions via `POST /stream` to `nexus_engine.py`, which handles all terminal UI output. Ears daemon runs silently with minimal status logging.
- **WSLg PulseAudio stale socket**: If `sounddevice` reports 0 devices, run `wsl --shutdown` from Windows PowerShell and restart
- **Stale CUDA context**: Resolved by switching from low-level `model.forward()` + `rnnt_decoder_predictions_tensor()` to high-level `model.transcribe()`
- **vLLM cold start**: First inference after container start is slow (60s timeout handles this)
- **NeMo tqdm spam**: Suppressed with `verbose=False` + `redirect_stderr`

## Agent Personas

| Persona | Responsibility |
|---|---|
| **Archie** | Architecture audits, specs, implementation plans |
| **Scrubber** | Ensures no API keys, HF_TOKENs, or internal IPs leak to external logs or commits |
| **Vinci** | Telemetry dashboards, VRAM monitoring |
| **Proxy** | Latency benchmarking on the ASR→Brain loop |

## Plugin Usage

- **Serena**: Semantic code navigation and symbol-level edits
- **Context7**: Fetch current docs for NeMo, vLLM, Silero, sounddevice
- **Playwright**: UI/E2E testing for any future dashboard (Vinci)
- **Commit-Commands**: Structured commits after each agent task completes

## Security Rules (Scrubber)

- Never log, print, or commit values matching: `hf_*`, `sk-*`, or the Docker bridge IP (`172.17.0.1`) to any external service
- Configs with secrets must go in `.env` and be gitignored
- Use environment variables for all credentials; load via `os.environ`

## Development Workflow

1. Edit scripts on host under `~/nexus-engine/scripts/`
2. Changes are live-mounted into `seishin-ears` and `seishin-mouth` — no rebuild needed
3. Start ears daemon once: `bash run_shortcuts/run_ears.sh` (loads Parakeet + Silero, ~10s)
4. In a separate terminal, start nexus engine: `bash run_shortcuts/run.sh` (instant)
5. In a separate terminal, start mouth daemon: `bash run_shortcuts/run_mouth.sh` (loads Qwen3-TTS, ~10s; first run downloads ~4.54 GB)
6. To iterate on prompts/LLM logic: Ctrl+C nexus engine, edit, restart (~0.1s)
7. Run `docker logs seishin-brain -f` to monitor LLM container
8. Git remote: `git@github.com:pranavrp122/projectseishin.git` (branch: `main`)

---

# VAD Integration Spec — Silero VAD Gatekeeper

**Author**: Archie (Architecture Agent)
**Status**: Approved for Implementation
**Target file**: `scripts/nexus_engine.py`

---

## Problem Statement

The current implementation polls audio from a rolling 2-second buffer and uses a fixed
`SILENCE_THRESHOLD = 1.3s` timer to decide when the user has finished speaking. This approach
has two failure modes:

1. **Ghost words**: Parakeet runs on every buffer tick, including frames that contain only
   background noise or partial phonemes. The model hallucinates short tokens (`"the"`, `"a"`,
   `"um"`) which reset `last_speech_time` and prevent the silence gate from ever triggering.

2. **Fixed-latency bias**: 1.3 s is a worst-case guess. Fast utterances ("yes", "stop") always
   incur the full wait. Longer sentences may be cut early if the speaker pauses briefly mid-thought.

## Solution: Silero VAD as a Pre-ASR Gatekeeper

Silero VAD is a lightweight ONNX/Torch model (~1 MB) that outputs a speech probability score
per 512-sample chunk (32 ms at 16 kHz). Placing it before Parakeet means:

- Parakeet only runs on confirmed speech segments — eliminates ghost words
- Silence detection is driven by acoustic reality, not a wall-clock timer
- CPU-resident — zero GPU contention with Parakeet

## Architecture

```
Mic callback (800-sample chunks @ 16 kHz)
        │
        ▼
[ VAD Ring Buffer ]  ← accumulate until full chunk (512 samples)
        │
        ▼
[ Silero VAD ]  (CPU, torch.hub model in inference mode)
  speech_prob per chunk
        │
   ┌────┴────┐
   │         │
 > 0.5     ≤ 0.5
(speech)  (silence)
   │         │
   ▼         └──── silence_counter++
[ Append to ASR buffer ]
   │              if silence_counter >= SILENCE_FRAMES:
   │                  → flush ASR buffer to Parakeet
   │                  → send to Brain
   │                  → reset all state
   ▼
[ Parakeet TDT ]  (GPU)
        │
        ▼
[ ask_brain() ]  (HTTP stream to vLLM)
```

## Parameters

| Parameter | Value | Rationale |
|---|---|---|
| `VAD_CHUNK_SAMPLES` | `512` | Silero's required chunk size at 16 kHz |
| `VAD_SAMPLE_RATE` | `16000` | Must match mic and Parakeet |
| `VAD_SPEECH_THRESHOLD` | `0.5` | Silero default; tune down to 0.35 for noisy rooms |
| `VAD_SILENCE_FRAMES` | `15` | 15 × 32 ms = ~480 ms of silence → end of utterance |
| `VAD_MIN_SPEECH_FRAMES` | `5` | Ignore bursts shorter than 5 frames (~160 ms); filters clicks |
| `VAD_MAX_BUFFER_SECONDS` | `10` | Hard cap on ASR buffer to prevent memory growth |

`VAD_SILENCE_FRAMES = 15` replaces the old `SILENCE_THRESHOLD = 1.3`. The effective silence
gate is now 480 ms, which is empirically fast for natural conversation while still robust to
brief mid-sentence pauses (which typically last < 300 ms).

## State Machine

```
IDLE
  │  speech_prob > VAD_SPEECH_THRESHOLD for >= VAD_MIN_SPEECH_FRAMES
  ▼
SPEAKING  ← append chunk to asr_buffer, reset silence_counter
  │  speech_prob <= VAD_SPEECH_THRESHOLD
  ▼
TRAILING  ← silence_counter++
  │  silence_counter >= VAD_SILENCE_FRAMES
  ▼
FLUSH  → run Parakeet on asr_buffer → ask_brain() → back to IDLE
  │  speech_prob > VAD_SPEECH_THRESHOLD (user starts again before flush)
  ▼
SPEAKING  (re-enter, keep accumulated buffer)
```

## Model Loading

```python
# Load once at startup — CPU-resident, inference mode
vad_model, vad_utils = torch.hub.load(
    repo_or_dir='snakers4/silero-vad',
    model='silero_vad',
    force_reload=False
)
(get_speech_timestamps, _, _, VADIterator, _) = vad_utils
vad_model.train(False)  # put model in inference mode (equivalent to model.eval())
```

`torch.hub` caches the model in `~/.cache/torch/hub/`. Inside the container, ensure the
cache directory is writable or pre-seeded to avoid re-downloading on each restart.

## Removed Code

The following logic is **deleted** in the new implementation:

- `SILENCE_THRESHOLD = 1.3` constant
- `last_speech_time` variable
- `last_text` deduplication guard (ghost-word workaround)
- The full Parakeet decode-on-every-tick loop

## Container Constraints

- Silero loads via `torch.hub` — requires internet access on first run, or a pre-cached model
- The NeMo 26.02 image ships with PyTorch >= 2.0, which is compatible with Silero
- No new pip installs required; `onnxruntime` is optional (Silero uses native Torch by default)

## Testing Criteria

| Test | Pass Condition |
|---|---|
| Background noise only | No ASR invocations over 30 s |
| Single word ("stop") | Exactly 1 ASR + 1 Brain call within 700 ms of word end |
| Natural sentence | Flush triggers <= 600 ms after trailing silence |
| Mid-sentence pause (< 300 ms) | No premature flush |
| Max buffer guard | Buffer capped at `VAD_MAX_BUFFER_SECONDS × RATE` samples |
