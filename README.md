# Project Seishin

Voice-driven AI companion with real-time speech recognition, LLM conversation, and emotional text-to-speech. Split architecture: GPU server handles all inference, lightweight client runs on any laptop.

## Architecture

```
Laptop (Client)                         GPU Server
+-----------------------+               +---------------------------+
| Seishin Client        |   WebSocket   | Nexus Engine (port 5052)  |
| - Mic capture         | <-----------> | - Parakeet TDT ASR        |
| - Silero VAD          |   (or ngrok)  | - Gemma 4 LLM (8000)      |
| - Audio playback      |               | - Fish Speech TTS (8080)  |
+-----------------------+               +---------------------------+
```

The server runs three components as Docker containers:

- **seishin-ears**: `ears_daemon.py` (Parakeet TDT ASR + Silero VAD) + `nexus_engine.py` (HTTP engine, port 5050)
- **vllm-gemma4**: Gemma 4 26B-A4B NVFP4 via vLLM (port 8000)
- **seishin-mouth**: Fish Speech API server (port 8080)

- **Client**: Captures mic audio, runs VAD to detect speech, streams PCM to server, plays back TTS audio
- **Server**: Transcribes speech (Parakeet TDT), generates response (Gemma 4), synthesizes voice (Fish Speech), streams audio back

## Server Setup (Linux with NVIDIA GPU)

Requires an NVIDIA GPU with 24GB+ VRAM (tested on RTX 5090 32GB).

### Prerequisites

- Python 3.12+
- NVIDIA drivers + CUDA toolkit
- Docker with NVIDIA Container Toolkit

### 1. Clone and set up Python environment

```bash
git clone https://github.com/pranavrp122/project-seishin.git
cd project-seishin
python -m venv .venv
source .venv/bin/activate
pip install websockets httpx ormsgpack
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set SEI_AUTH_TOKEN and any other required vars
```

### 3. Start the LLM (Gemma 4 via vLLM)

```bash
cd gemma4-test
./run.sh tq
# Wait for "INFO: Application startup complete" — runs on port 8000
```

### 4. Set up and start the ears container (Parakeet ASR)

```bash
# First time only — build image and create container
bash run_shortcuts/setup_ears.sh

# Start the ears daemon (loads Parakeet TDT + Silero VAD, ~10s)
bash run_shortcuts/run_ears.sh
```

### 5. Start the Nexus Engine

```bash
# In a separate terminal — restarts in ~0.1s for fast iteration
bash run_shortcuts/run.sh
```

### 6. Start Fish Speech TTS (port 8080)

```bash
# In a separate terminal
bash run_shortcuts/run_fish_api.sh
# Runs in seishin-mouth container on port 8080 with reference voice "archie"
```

### 7. Expose via ngrok (for remote clients)

```bash
ngrok http 5052
# Note the https:// URL — clients connect with wss://
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SEI_AUTH_TOKEN` | (required) | Bearer token for client auth |
| `SEI_BIND` | `127.0.0.1` | Bind address |
| `SEI_PORT` | `5052` | WebSocket port |
| `SEI_LLM_URL` | `http://127.0.0.1:8000` | vLLM endpoint |
| `SEI_MODEL_NAME` | `gemma-4` | Model name for vLLM |
| `SEI_TTS_URL` | `http://127.0.0.1:8080` | Fish Speech endpoint |
| `SEI_DEV_MODE` | `0` | Set to `1` to use default dev token |
| `TTS_REFERENCE_ID` | `archie` | Fish Speech reference voice |

## Client Setup

The client is a Tauri desktop app (Rust + TypeScript). It can also run as a web app in the browser during development.

### Prerequisites (all platforms)

- Node.js 18+
- npm or pnpm

### Additional prerequisites for Tauri builds

**macOS:**
```bash
xcode-select --install
```

**Windows:**
- Visual Studio Build Tools with C++ workload
- WebView2 (comes with Windows 10/11)
- Rust: https://rustup.rs

**Linux:**
```bash
# Ubuntu/Debian
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file \
  libssl-dev libayatana-appindicator3-dev librsvg2-dev

# Fedora
sudo dnf install webkit2gtk4.1-devel openssl-devel curl wget file \
  libappindicator-gtk3-devel librsvg2-devel

# Rust (all Linux)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### Install dependencies

```bash
cd seishin-client
npm install
npm run prebuild   # copies VAD model + ONNX runtime to public/
```

### Run in browser (dev mode)

```bash
npm run dev
# Opens at http://localhost:5173
# Enter the server WebSocket URL (ws://IP:5052 or wss://ngrok-url)
# Enter the auth token
```

### Build Tauri desktop app

```bash
npm run tauri build
# Output binary in src-tauri/target/release/
```

## Connecting

1. Start all server services (LLM, ears daemon, nexus engine, Fish Speech)
2. Start the client (dev server or Tauri app)
3. Enter the WebSocket URL:
   - Local: `ws://SERVER_IP:5052`
   - Remote via ngrok: `wss://your-ngrok-url.ngrok-free.dev`
4. Enter the auth token (must match `SEI_AUTH_TOKEN` on server)
5. Click connect, grant mic permission, and start talking

## How It Works

1. Client mic captures audio, Silero VAD detects when you start/stop speaking
2. Raw PCM16 audio streams to server in real-time over WebSocket
3. Server runs Parakeet TDT live transcription during speech — result is cached and KV-prefilled into the LLM
4. When speech ends, cached transcript is sent to Gemma 4 LLM instantly
5. LLM response gets emotion tags converted for Fish Speech (e.g. `(happy)` prefix)
6. Fish Speech generates TTS audio, streamed back to client as PCM chunks
7. Client plays audio in real-time
8. If user starts speaking during playback, the server interrupts generation and TTS immediately
