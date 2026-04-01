# Nexus Engine — Claude Code Context

## System Architecture

Nexus Engine is a zero-latency, voice-driven conversational AI split across two Docker containers communicating over the Docker bridge network.

```
[ Mic (host /dev/snd) ]
        │
[ seishin-ears ] ─── ASR (Parakeet TDT 1.1B via NeMo) + VAD (Silero)
        │  HTTP POST
[ seishin-brain ] ── LLM inference (vLLM serving Qwen/Qwen3.5-9B)
        │
[ stdout / TTS (future) ]
```

## Docker Containers

| Container | Image | Port | Role |
|---|---|---|---|
| `seishin-brain` | `vllm/vllm-openai:latest` | `8001` | LLM inference |
| `seishin-ears` | `nvcr.io/nvidia/nemo:26.02` | — | ASR + VAD pipeline |

- Bridge IP for inter-container communication: `172.17.0.1`
- `seishin-ears` mounts `~/nexus-engine/scripts` → `/workspace/scripts`
- `seishin-ears` requires `--device /dev/snd` for direct microphone access

## Hardware Constraints (RTX 5090)

- GPU: NVIDIA RTX 5090, 32 GB VRAM
- vLLM is configured with `gpu_memory_utilization=0.8`, leaving ~6 GB headroom
- Parakeet TDT 1.1B runs on the same GPU via NeMo inside `seishin-ears`
- Silero VAD runs on CPU to avoid contention with Parakeet on the GPU
- Never load two large models concurrently without profiling VRAM headroom first

## Key Files

| Path | Purpose |
|---|---|
| `scripts/nexus_engine.py` | Main pipeline: VAD → ASR → LLM |
| `docs/vad_spec.md` | Silero VAD integration spec |
| `docs/TASKS.md` | Agent task roadmap |
| `configs/` | Reserved for model/runtime configs |
| `logs/` | Runtime logs |
| `.agents/rules/` | Agent behavioral rules |

## Agent Personas

| Persona | Responsibility |
|---|---|
| **Archie** | Architecture audits, specs, implementation plans |
| **Scrubber** | Ensures no API keys, HF_TOKENs, or internal IPs leak to external logs or commits |
| **Vinci** | Telemetry dashboards, VRAM monitoring |
| **Proxy** | Latency benchmarking on the ASR→Brain loop |

## Security Rules (Scrubber)

- Never log, print, or commit values matching: `hf_*`, `sk-*`, or the Docker bridge IP (`172.17.0.1`) to any external service
- Configs with secrets go in `configs/` and must be `.gitignore`d
- Use environment variables for all credentials; load via `os.environ`

## Plugin Usage

- **Serena**: Semantic code navigation and symbol-level edits
- **Context7**: Fetch current docs for NeMo, vLLM, Silero, sounddevice
- **Playwright**: UI/E2E testing for any future dashboard (Vinci)
- **Commit-Commands**: Structured commits after each agent task completes

## LLM Endpoint

- URL: `http://172.17.0.1:8001/v1/completions`
- Model: `Qwen/Qwen3.5-9B`
- Streaming: enabled (`stream=True`)
- Stop tokens: `["User:", "\n"]`

## Development Workflow

1. Edit scripts on host under `~/nexus-engine/scripts/`
2. Changes are live-mounted into `seishin-ears` — no rebuild needed
3. Restart the Python process inside the container to pick up changes
4. Run `docker logs seishin-ears -f` to monitor output
