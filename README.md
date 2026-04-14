# Nexus Engine 🚀

A zero-latency, voice-driven conversational AI framework splitting Auto Speech Recognition (ASR) and Large Language Model (LLM) inference across dual Docker containers, optimizing an NVIDIA RTX 5090's 32GB VRAM.

## Architecture
- **🎙️ The Ears (`seishin-ears`)**: Runs NVIDIA's `Parakeet-tdt-0.6b-v2` for fast ASR, listening to host microphone input.
- **🧠 The Brain (`seishin-brain`)**: Runs `Qwen3.5-9B` FP8 served on a `vLLM` HTTP instance, responding to Parakeet's parsed transcripts.
- **🗣️ The Mouth (`seishin-mouth`)**: Runs `Qwen3-TTS 1.7B` BF16 with Hybrid Triton mode for streaming text-to-speech via Bluetooth headphones.

## Prerequisites
- NVIDIA Driver + WSL2 (with WSLg PulseAudio integration).
- Docker and NVIDIA Container Toolkit installed.
- RTX 5090 (or similar 24GB+ VRAM GPU).

## Setup & Testing Quickstart

### 1. Configure the Environment
Copy the newly created `.env` file to your environment, inserting any required configuration values.
```bash
cp .env.example .env
```
*(The repository natively expects `.env` files to be `.gitignore`'d for security. Never commit `.env` or API keys!)*

### 2. Run the Engine!
The system uses a fast decoupled Client-Daemon architecture.

**First, start the Brain (vLLM server):**
This brings up the Qwen3.5-9B server. Wait a minute for the Brain to boot up fully and compile its PyTorch execution graphs the first time.
```bash
./run_shortcuts/run_brain.sh
# Or use the shortcut:
brain
```

**Second, start the Ears Daemon (runs in background):**
This loads the heavy Parakeet ASR model and Silero VAD into memory (~10 seconds boot time). Run this in another terminal:
```bash
./run_shortcuts/run_ears.sh
# Or use the shortcut:
ears
```

**Third, start the Mouth Daemon (TTS):**
This loads Qwen3-TTS with Hybrid Triton mode (~10 seconds boot, first run downloads ~4.54 GB). Run this in another terminal:
```bash
./run_shortcuts/run_mouth.sh
# Or use the shortcut:
mouth
```

**Fourth, start the Nexus Engine (the Brain Logic):**
This is a lightweight logic controller that connects the ears to the LLM. It restarts instantly so you can rapidly iterate on your AI's persona without waiting for models to load. Run this in a final terminal:
```bash
./run_shortcuts/run.sh
# Or use the shortcut:
nexus
```

## Engine Usage
Once the `nexus` script outputs `NEXUS ENGINE ONLINE — listening on port 5050`:
- **Hands-Free Mode:** Just begin talking into your microphone!
- The intelligent Silero VAD gatekeeper monitors your audio, ignoring PC fans and background hums.
- The Engine captures UNBOUNDED audio while you are speaking.
- The moment you pause speaking, the phrase is transcribed and sent to the Brain automatically (no Enter key needed!).
- Say **"Nexus clear memory"** to reset conversation history without restarting.

## Current Agent Workflows (GSD Framework)
- Refer to `docs/TASKS.md` for our current objectives.
- Refer to `docs/FIXES.md` for historical bugs tracking (like ALSA misconfigurations and VRAM overheads).
- Run the GSD base agent by invoking `claude` in the root directory.
