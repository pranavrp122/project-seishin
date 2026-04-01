# Nexus Engine — Claude Code Context

## System Architecture

Nexus Engine is a zero-latency, voice-driven conversational AI using a client-daemon architecture for instant dev iteration. The system spans two Docker containers plus an internal HTTP bridge between the ears daemon and the nexus engine.

```
[ Mic (host PulseAudio via WSLg) ]
        │
[ ears_daemon.py ] ─── Silero VAD (CPU) + Parakeet TDT 1.1B (GPU)
        │  HTTP POST to localhost:5050
        │  /prefill (fire-and-forget during speech)
        │  /flush   (blocking, after silence detected)
        │
[ nexus_engine.py ] ─── Lightweight HTTP server (port 5050, zero ML models)
        │  HTTP POST (streaming)
[ seishin-brain ] ──── LLM inference (vLLM serving Qwen/Qwen3.5-9B)
        │
[ stdout / TTS (future) ]
```

Both `ears_daemon.py` and `nexus_engine.py` run inside `seishin-ears`. The daemon loads heavy models once and stays running. The engine can be restarted in ~0.1s to iterate on prompts, history logic, or generation params without reloading models.

## Pipeline Flow

1. `ears_daemon.py` captures mic audio at 16kHz via `sounddevice.InputStream`
2. Silero VAD (CPU) classifies 512-sample chunks as speech/silence
3. VAD state machine: IDLE → SPEAKING → TRAILING → FLUSH
4. During SPEAKING/TRAILING, Parakeet runs live transcription and sends it via `POST /stream` to nexus engine
5. Every 4 new words, ears daemon sends `POST /prefill` to warm vLLM's KV cache
6. On FLUSH (480ms silence), ears daemon sends `POST /flush` to nexus engine
7. `nexus_engine.py` displays live transcription via `/stream`, receives flush, calls `ask_brain()` which streams the Qwen response to stdout
8. Nexus engine manages conversation history, response quality filtering, and TTFT counters

## Docker Containers

| Container | Image | Port | Role |
|---|---|---|---|
| `seishin-brain` | `vllm/vllm-openai:latest` | `8001` | LLM inference |
| `seishin-ears` | `nvcr.io/nvidia/nemo:26.02` | — | ASR pipeline |

- Bridge IP for inter-container communication: `172.17.0.1`
- `seishin-ears` mounts `~/nexus-engine/scripts` → `/workspace/scripts`
- `seishin-ears` runs with `--privileged` flag for audio device access
- `seishin-ears` requires PulseAudio socket: `-v /mnt/wslg:/mnt/wslg -e PULSE_SERVER=unix:/mnt/wslg/PulseServer`

## Hardware Constraints (RTX 5090)

- GPU: NVIDIA RTX 5090, 32 GB VRAM
- vLLM is configured with `gpu_memory_utilization=0.8`, leaving ~6 GB headroom
- Parakeet TDT 1.1B runs on the same GPU via NeMo inside `seishin-ears`
- Never load two large models concurrently without profiling VRAM headroom first

## Key Files

| Path | Purpose |
|---|---|
| `scripts/ears_daemon.py` | Heavy daemon: Mic → Silero VAD → Parakeet ASR → HTTP to nexus engine |
| `scripts/nexus_engine.py` | Lightweight engine: HTTP server (port 5050) → conversation history → vLLM |
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
- System prompt enforces "Nexus" persona with anti-repetition and brevity instructions
- Response quality filter drops garbage replies (dodge phrases) to prevent history poisoning

## ASR Configuration

- Model: `nvidia/parakeet-tdt-1.1b` loaded via `nemo_asr.models.ASRModel.from_pretrained()`
- Inference: `model.transcribe([buffer], batch_size=1, verbose=False)`
- tqdm progress bar suppressed via `contextlib.redirect_stderr(io.StringIO())`
- Sample rate: 16000 Hz, blocksize: 800
- Silero VAD gatekeeper: 512-sample chunks, speech threshold 0.5, 480ms silence gate
- VAD runs on CPU, Parakeet on GPU — zero contention

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
2. Changes are live-mounted into `seishin-ears` — no rebuild needed
3. Start ears daemon once: `python /workspace/scripts/ears_daemon.py` (loads models, ~10s)
4. In a separate terminal, start nexus engine: `python /workspace/scripts/nexus_engine.py` (instant)
5. To iterate on prompts/LLM logic: Ctrl+C nexus engine, edit, restart (~0.1s)
6. Run `docker logs seishin-brain -f` to monitor LLM container
7. Git remote: `git@github.com:pranavrp122/projectseishin.git` (branch: `main`)
