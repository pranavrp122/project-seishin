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
You can execute the primary application script via our convenient bash alias wrapper (`nexus`), or manually via the mounted script directory:

```bash
docker exec -it seishin-ears python3 /workspace/scripts/nexus_engine.py
```
*Note: Wait a minute for the Brain to boot up fully and compile its PyTorch execution graphs the first time you run it.*

## Engine Usage
Once the script says `🚀 NEXUS ENGINE UPDATED. Speak into the mic.`:
- Begin talking into your microphone.
- You will see Parakeet transcribe your speech dynamically on stream.
- The Engine captures UNBOUNDED audio; you do not have to race a timer!
- Once you are ready to send your thought to the Brain, **Hit the `Enter` key**.

## Current Agent Workflows (GSD Framework)
- Refer to `docs/TASKS.md` for our current objectives.
- Refer to `docs/FIXES.md` for historical bugs tracking (like ALSA misconfigurations and VRAM overheads).
- Run the GSD base agent by invoking `claude` in the root directory.
