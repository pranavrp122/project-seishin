# Project Seishin

Voice-driven AI companion with real-time speech recognition, LLM conversation, and emotional text-to-speech. Split architecture: GPU server handles all inference, lightweight client runs on any laptop.

## Architecture

```
Laptop (Client)                         GPU Server
+-----------------------+               +---------------------------+
| Seishin Client        |   WebSocket   | Sei Engine (port 5052)    |
| - Mic capture         | <-----------> | - whisper.cpp ASR (9876)  |
| - Silero VAD          |   (or ngrok)  | - Gemma 4 LLM (8000)     |
| - Audio playback      |               | - Fish Speech TTS (8080)  |
+-----------------------+               +---------------------------+
```

- **Client**: Captures mic audio, runs VAD to detect speech, streams PCM to server, plays back TTS audio
- **Server**: Transcribes speech (whisper.cpp), generates response (Gemma 4), synthesizes voice (Fish Speech), streams audio back

## Server Setup (Linux with NVIDIA GPU)

Requires an NVIDIA GPU with 24GB+ VRAM (tested on RTX 5090 32GB).

### Prerequisites

- Python 3.12+
- NVIDIA drivers + CUDA toolkit
- Docker (for vLLM and Fish Speech)

### 1. Clone and set up Python environment

```bash
git clone https://github.com/pranavrp122/project-seishin.git
cd project-seishin
python -m venv .venv
source .venv/bin/activate
pip install websockets httpx ormsgpack
```

### 2. Start the LLM (Gemma 4 via vLLM)

```bash
# Adjust model path and quantization for your GPU
cd gemma4-test
./run.sh tq
# Wait for "INFO: Application startup complete" — runs on port 8000
```

### 3. Start Fish Speech TTS (port 8080)

```bash
cd fish-speech
docker compose up -d
# Runs on port 8080 with reference voice "archie"
```

### 4. Start whisper.cpp ASR server (port 9876)

```bash
# Build whisper.cpp with CUDA support first (see whisper.cpp docs)
cd whisper.cpp
./build/bin/whisper-server -m models/ggml-large-v3-turbo.bin --port 9876 -ng
```

### 5. Start the Sei Engine

```bash
cd project-seishin
source .venv/bin/activate
SEI_AUTH_TOKEN=your-secret-token python scripts/sei_engine.py
# Listens on 127.0.0.1:5052
```

### 6. Expose via ngrok (for remote clients)

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
| `SEI_ASR_URL` | `http://127.0.0.1:9876` | whisper.cpp endpoint |
| `SEI_MAX_TOKENS` | `300` | Max LLM response tokens |
| `SEI_TEMPERATURE` | `0.7` | LLM temperature |
| `SEI_DEV_MODE` | `0` | Set to `1` to use default dev token |

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

1. Start all server services (LLM, TTS, ASR, Sei Engine)
2. Start the client (dev server or Tauri app)
3. Enter the WebSocket URL:
   - Local: `ws://SERVER_IP:5052`
   - Remote via ngrok: `wss://your-ngrok-url.ngrok-free.dev`
4. Enter the auth token (must match `SEI_AUTH_TOKEN` on server)
5. Click connect, grant mic permission, and start talking

## How It Works

1. Client mic captures audio, Silero VAD detects when you start/stop speaking
2. Raw PCM16 audio streams to server in real-time over WebSocket
3. Server runs whisper.cpp live transcription during speech (result is cached)
4. When speech ends, cached transcript is sent to Gemma 4 LLM instantly
5. LLM response gets emotion tags converted for Fish Speech (e.g. `(happy)` to `[happy]`)
6. Fish Speech generates TTS audio, streamed back to client as PCM chunks
7. Client plays audio in real-time
