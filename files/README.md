# Project Seishin — Phase 1: Voice Pipeline

> Parakeet STT → Qwen 3.5 → Fish Audio TTS  
> Target: **<150ms voice-to-voice latency**

---

## Prerequisites

- WSL2 with CUDA 12.6+ (`nvcc --version` to verify)
- RTX 5090 drivers installed and visible to WSL2
- Python 3.11+
- `nc` (netcat) for health checks: `sudo apt install netcat`

---

## 1. Install Python Dependencies

```bash
pip install aiohttp websockets sounddevice soundfile numpy
```

**vLLM** (must be installed separately for CUDA support):
```bash
pip install vllm
```

**Fish Speech** (local TTS server):
```bash
git clone https://github.com/fishaudio/fish-speech
cd fish-speech && pip install -e .
# Download checkpoints:
huggingface-cli download fishaudio/fish-speech-1.5 --local-dir checkpoints/fish-speech-1.5
```

---

## 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Get from https://build.nvidia.com/ (free tier available)
NIM_API_KEY=nvapi-xxxxxxxxxxxx

# Fish Audio voice ID (optional — leave blank for default voice)
FISH_REFERENCE_ID=
```

---

## 3. Start Everything

```bash
chmod +x scripts/*.sh
./scripts/start.sh
```

This will:
1. Launch **vLLM** with Qwen 3.5 35B on the RTX 5090
2. Launch **Fish Audio** TTS server
3. Serve the **dashboard** at `http://localhost:3000`
4. Start the **pipeline** (mic → STT → LLM → TTS → speaker)

---

## 4. Open the Dashboard

```
http://localhost:3000
```

---

## Architecture

```
Microphone
    │
    ▼
[VAD — Energy-based silence detection]
    │  (end of utterance detected)
    ▼
[Parakeet TDT 1.1B — NVIDIA NIM]
    │  transcript text
    ▼
[Qwen 3.5 35B — vLLM streaming]
    │  tokens (streamed)
    ▼
[Sentence Chunker]
    │  first complete sentence → TTS immediately
    │  subsequent sentences → TTS as they complete
    ▼
[Fish Audio S2-Pro — local]
    │  streaming audio chunks
    ▼
[Speaker]
```

**Key latency optimizations:**
- LLM streams tokens; TTS starts on the *first complete sentence* (not the full response)
- Fish Audio streams audio chunks; playback starts on first chunk
- Async WebSocket bridge means the dashboard never blocks the pipeline
- vLLM prefix caching + speculative decoding (0.5B drafter) for faster LLM throughput
- CUDA Graphs enabled for RTX 5090 (Blackwell)
- FP8 KV cache for long-context efficiency

---

## Upgrading VAD

The default VAD is energy-based (no dependencies). For production accuracy:

```bash
pip install silero-vad torch torchaudio
```

Then in `pipeline.py`, swap `SimpleVAD` for `SileroVAD`:

```python
# Replace SimpleVAD with:
from silero_vad import load_silero_vad, get_speech_timestamps
```

---

## Phase Roadmap

- **Phase 1 (current):** Voice-to-voice pipeline + dashboard
- **Phase 2:** OmniVideo-R1 vision + Pinecone/Milvus memory
- **Phase 3:** Epstein Generativity Theory emotion layer + RVC V2 voice identity
- **Phase 4:** Unity 3D character via WebSocket + Motion-R1
- **Phase 5:** Full emotional weight → blendshapes + poses + voice
- **Phase 6:** OpenClaw agentic capabilities
