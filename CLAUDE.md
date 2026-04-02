# Nexus Engine — Claude Code Context

## System Architecture

Nexus Engine is a zero-latency, voice-driven conversational AI using a client-daemon architecture for instant dev iteration. The system spans three Docker containers with HTTP bridges between ears, nexus engine, and mouth daemons.

```
[ Mic (host PulseAudio via WSLg) ]
        │
[ ears_daemon.py ] ─── Silero VAD (CPU) + Parakeet TDT 1.1B (GPU)
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
4. During SPEAKING/TRAILING, Parakeet runs live transcription and sends it via `POST /stream` to nexus engine
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
| Parakeet TDT 1.1B | seishin-ears | FP16 (CPU→FP16→CUDA) | `torch.cuda.set_per_process_memory_fraction(0.12)` | ~3.9 GB cap (~2.1 GB actual) |
| Qwen3-TTS 1.7B | seishin-mouth | BF16 | `torch.cuda.set_per_process_memory_fraction(0.18)` | ~5.9 GB cap (~4.3 GB actual) |
| **Total** | | | | **~27.7 GB actual / 32 GB** |

- FP8 quantization halves Qwen3.5-9B model weights from ~18 GB to ~10.8 GB (natively supported on Blackwell)
- `PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512` (mouth) / `256` (ears) prevents memory fragmentation
- Never load additional large models without profiling VRAM headroom first

## Key Files

| Path | Purpose |
|---|---|
| `scripts/ears_daemon.py` | Heavy daemon: Mic → Silero VAD → Parakeet ASR → HTTP to nexus engine; fires /stop on interrupt |
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

- Model: `nvidia/parakeet-tdt-1.1b` loaded via `nemo_asr.models.ASRModel.from_pretrained()`
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
