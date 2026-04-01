# Nexus Engine — Claude Code Context

## System Architecture

Nexus Engine is a zero-latency, voice-driven conversational AI split across two Docker containers communicating over the Docker bridge network.

```
[ Mic (host PulseAudio via WSLg) ]
        │
[ seishin-ears ] ─── ASR (Parakeet TDT 1.1B via NeMo model.transcribe())
        │  HTTP POST (streaming)
[ seishin-brain ] ── LLM inference (vLLM serving Qwen/Qwen3.5-9B)
        │
[ stdout / TTS (future) ]
```

## Pipeline Flow

1. `sounddevice.InputStream` captures mic audio at 16kHz, queuing chunks
2. Chunks accumulate in a numpy buffer (unbounded — no buffer cap)
3. `model.transcribe([buffer])` runs Parakeet TDT 1.1B on the buffer continuously
4. Live transcription is shown in the terminal via `\r` overwrite
5. User presses **Enter** to flush the buffer to the LLM (no silence threshold)
6. `ask_brain()` sends a few-shot prompt to vLLM's `/v1/completions` endpoint
7. vLLM streams the response back token-by-token, printed live to stdout

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
| `scripts/nexus_engine.py` | Main pipeline: Mic → ASR → LLM (Enter-to-send) |
| `docs/FIXES.md` | Bug fix log with numbered entries |
| `docs/TASKS.md` | Agent task roadmap |
| `README.md` | Setup guide for collaborators |
| `.env` | Environment config (gitignored) |
| `.gitignore` | Excludes .env, configs/, logs/, __pycache__/ |

## LLM Endpoint

- URL: `http://172.17.0.1:8001/v1/completions`
- Model: `Qwen/Qwen3.5-9B`
- Streaming: enabled (`stream=True`)
- Stop tokens: `["User:", "\n"]`
- Timeout: 60s (accommodates initial vLLM CUDA graph compilation)
- Few-shot prompt template enforces "Nexus Engine" persona

## ASR Configuration

- Model: `nvidia/parakeet-tdt-1.1b` loaded via `nemo_asr.models.ASRModel.from_pretrained()`
- Inference: `model.transcribe([buffer], batch_size=1, verbose=False)`
- tqdm progress bar suppressed via `contextlib.redirect_stderr(io.StringIO())`
- Sample rate: 16000 Hz, blocksize: 800
- No silence threshold — Enter key is the only send trigger

## Known Issues & Fixes

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
- Configs with secrets go in `configs/` and must be `.gitignore`d
- Use environment variables for all credentials; load via `os.environ`

## Development Workflow

1. Edit scripts on host under `~/nexus-engine/scripts/`
2. Changes are live-mounted into `seishin-ears` — no rebuild needed
3. Run `nexus` alias (or `python /workspace/scripts/nexus_engine.py` inside container) to start
4. Run `docker logs seishin-brain -f` to monitor LLM container
5. Git remote: `git@github.com:pranavrp122/projectseishin.git` (branch: `main`)
