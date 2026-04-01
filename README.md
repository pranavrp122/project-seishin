# Nexus Engine 🚀

A zero-latency, voice-driven conversational AI framework splitting Auto Speech Recognition (ASR) and Large Language Model (LLM) inference across dual Docker containers, optimizing an NVIDIA RTX 5090's 32GB VRAM.

## Architecture
- **🎙️ The Ears (`seishin-ears`)**: Runs NVIDIA's `Parakeet-tdt-1.1b` for fast ASR, listening to host microphone input.
- **🧠 The Brain (`seishin-brain`)**: Runs `Qwen3.5-9B` served on a `vLLM` HTTP instance, responding to Parakeet's parsed transcripts.

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

### 2. Start the Docker Containers
Ensure both containers are brought online:
```bash
# Start the vLLM server on port 8001
docker start seishin-brain

# Start the NeMo Audio container
docker start seishin-ears
```

### 3. Run the Engine!
The system uses a fast two-part Client-Daemon architecture.

**First, start the Ears Daemon (runs in background):**
This loads the heavy Parakeet ASR model and Silero VAD into memory (~10 seconds boot time). Run this in one terminal:
```bash
./run_shortcuts/run_ears.sh
# Or use the shortcut:
ears
```

**Second, start the Nexus Engine (the Brain Logic):**
This is a lightweight logic controller that connects the ears to the LLM. It restarts instantly so you can rapidly iterate on your AI's persona without waiting for models to load. Run this in a second terminal:
```bash
./run_shortcuts/run.sh
# Or use the shortcut:
nexus
```
*Note: Wait a minute for the Brain to boot up fully and compile its PyTorch execution graphs the first time you run it.*

## Engine Usage
Once the `nexus` script outputs `NEXUS ENGINE ONLINE — listening on port 5050`:
- **Hands-Free Mode:** Just begin talking into your microphone!
- The intelligent Silero VAD gatekeeper monitors your audio, ignoring PC fans and background hums.
- The Engine captures UNBOUNDED audio while you are speaking.
- The moment you pause speaking, the phrase is transcribed and sent to the Brain automatically (no Enter key needed!).

## Current Agent Workflows (GSD Framework)
- Refer to `docs/TASKS.md` for our current objectives.
- Refer to `docs/FIXES.md` for historical bugs tracking (like ALSA misconfigurations and VRAM overheads).
- Run the GSD base agent by invoking `claude` in the root directory.
