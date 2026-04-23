#!/usr/bin/env python3
"""Voice Bridge — WebSocket proxy between phone/client audio and sei_engine.

Flow:
  Client sends PCM16 16kHz mono binary frames (any chunk size)
  VAD detects speech boundaries -> sends speech_start/speech_end to sei_engine
  sei_engine handles STT + LLM + Fish Speech TTS
  Binary PCM16 44.1kHz frames from sei_engine -> forwarded to client + buffered for call log
  On disconnect -> WAV saved, transcript + audio POSTed to OpenClaw

Client sends:    binary  PCM16 16kHz mono frames
Client sends:    JSON    {"type": "barge_in"}        interrupt AI mid-speech
Client sends:    JSON    {"type": "transcript", "text": "..."}  pre-transcribed text (optional)
Client receives: binary  PCM16 44.1kHz mono frames (Fish Speech output, streamed as generated)
Client receives: JSON    {"type": "transcript",  "text": "..."}
Client receives: JSON    {"type": "reply",       "text": "..."}
Client receives: JSON    {"type": "speaking",    "state": "start"|"end"}
Client receives: JSON    {"type": "error",       "message": "..."}
"""
import asyncio
import json
import os
import time
import uuid
import wave
import io
import numpy as np
import httpx
import torch
import websockets
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config (from env)
# ---------------------------------------------------------------------------
SEI_WS_URL   = os.environ.get("SEI_WS_URL",    "ws://127.0.0.1:5052")
SEI_AUTH     = os.environ.get("SEI_AUTH_TOKEN", "")
OPENCLAW_URL = os.environ.get("OPENCLAW_URL",   "")   # empty = local log only
BIND_HOST    = os.environ.get("BRIDGE_HOST",    "0.0.0.0")
BIND_PORT    = int(os.environ.get("BRIDGE_PORT", "7000"))
LOG_DIR      = Path(os.environ.get("BRIDGE_LOG_DIR", Path(__file__).parent / "call_logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# VAD config (matches ears_daemon)
# ---------------------------------------------------------------------------
VAD_CHUNK    = 512    # Silero requires exactly 512 samples at 16kHz
VAD_RATE     = 16000
VAD_THRESH   = 0.5
VAD_SILENCE  = 15     # 15 x 32ms = ~480ms silence -> speech end
VAD_MIN_SPCH = 5      # ignore bursts < 5 frames (~160ms)

# ---------------------------------------------------------------------------
# Load Silero VAD once at startup
# ---------------------------------------------------------------------------
print("Loading Silero VAD...", flush=True)
_vad_model, _ = torch.hub.load(
    repo_or_dir="snakers4/silero-vad",
    model="silero_vad",
    force_reload=False,
    verbose=False,
)
_vad_model.eval()
print("VAD ready.", flush=True)


def _vad_prob(samples: np.ndarray) -> float:
    t = torch.from_numpy(samples.astype(np.float32))
    with torch.no_grad():
        return float(_vad_model(t, VAD_RATE).item())


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------
def _pcm16_to_float(raw: bytes) -> np.ndarray:
    n = len(raw) // 2
    return np.frombuffer(raw[:n * 2], dtype=np.int16).astype(np.float32) / 32768.0


def _build_wav(pcm_bytes: bytes, sample_rate: int = 44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Call log
# ---------------------------------------------------------------------------
class CallLog:
    def __init__(self, call_id: str):
        self.call_id = call_id
        self.started = datetime.now(timezone.utc)
        self.turns: list[dict] = []
        self._audio: list[bytes] = []

    def add_turn(self, role: str, text: str):
        self.turns.append({
            "role": role,
            "text": text,
            "time": datetime.now(timezone.utc).isoformat(),
        })

    def add_audio(self, chunk: bytes):
        self._audio.append(chunk)

    def duration(self) -> float:
        return (datetime.now(timezone.utc) - self.started).total_seconds()

    async def save_and_send(self):
        duration  = self.duration()
        wav_bytes = _build_wav(b"".join(self._audio))
        ts        = self.started.strftime("%Y%m%d_%H%M%S")
        stem      = f"{ts}_{self.call_id[:8]}"

        (LOG_DIR / f"{stem}.wav").write_bytes(wav_bytes)
        (LOG_DIR / f"{stem}.json").write_text(json.dumps({
            "call_id":    self.call_id,
            "started_at": self.started.isoformat(),
            "duration":   duration,
            "transcript": self.turns,
        }, indent=2))
        print(f"[log] {stem}.wav  ({len(wav_bytes)//1024}KB, {duration:.0f}s)", flush=True)

        if OPENCLAW_URL:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        f"{OPENCLAW_URL}/api/call-log",
                        files={"audio": ("call_audio.wav", wav_bytes, "audio/wav")},
                        data={
                            "call_id":    self.call_id,
                            "started_at": self.started.isoformat(),
                            "duration":   str(duration),
                            "transcript": json.dumps(self.turns),
                        },
                    )
                print(f"[log] OpenClaw <- {resp.status_code}", flush=True)
            except Exception as exc:
                print(f"[log] OpenClaw POST failed: {exc}", flush=True)


# ---------------------------------------------------------------------------
# VAD state machine
# ---------------------------------------------------------------------------
class VADState:
    def __init__(self):
        self._buf        = bytearray()
        self._speech     = False
        self._silence    = 0
        self._spch_frms  = 0

    def reset(self):
        self._buf.clear()
        self._speech    = False
        self._silence   = 0
        self._spch_frms = 0

    def feed(self, raw: bytes) -> list[tuple[str | None, bytes]]:
        """Process raw bytes. Returns list of (event, chunk) pairs.
        event is 'speech_start', 'speech_end', or None (mid-speech frame).
        """
        self._buf.extend(raw)
        frame_bytes = VAD_CHUNK * 2
        events: list[tuple[str | None, bytes]] = []

        while len(self._buf) >= frame_bytes:
            frame = bytes(self._buf[:frame_bytes])
            del self._buf[:frame_bytes]
            prob  = _vad_prob(_pcm16_to_float(frame))

            if prob >= VAD_THRESH:
                self._silence    = 0
                self._spch_frms += 1
                if not self._speech and self._spch_frms >= VAD_MIN_SPCH:
                    self._speech = True
                    events.append(("speech_start", frame))
                elif self._speech:
                    events.append((None, frame))
            else:
                if self._speech:
                    self._silence += 1
                    events.append((None, frame))
                    if self._silence >= VAD_SILENCE:
                        self._speech    = False
                        self._silence   = 0
                        self._spch_frms = 0
                        events.append(("speech_end", b""))
                else:
                    self._spch_frms = 0

        return events


# ---------------------------------------------------------------------------
# Per-connection handler
# ---------------------------------------------------------------------------
async def handler(client_ws):
    call_id = str(uuid.uuid4())
    log     = CallLog(call_id)
    vad     = VADState()
    tag     = call_id[:8]

    print(f"[{tag}] connected from {client_ws.remote_address}", flush=True)

    headers = {"Authorization": f"Bearer {SEI_AUTH}"} if SEI_AUTH else {}

    try:
        async with websockets.connect(SEI_WS_URL, additional_headers=headers) as sei_ws:
            print(f"[{tag}] sei_engine connected", flush=True)

            reply_buf: list[str] = []
            speaking = False

            async def pump_sei():
                nonlocal speaking
                async for msg in sei_ws:
                    if isinstance(msg, bytes):
                        if not speaking:
                            speaking = True
                            await client_ws.send(json.dumps({"type": "speaking", "state": "start"}))
                        log.add_audio(msg)
                        await client_ws.send(msg)

                    elif isinstance(msg, str):
                        data = json.loads(msg)
                        t    = data.get("type")

                        if t == "sentence":
                            text = data.get("text", "")
                            reply_buf.append(text)
                            await client_ws.send(json.dumps({"type": "reply", "text": text}))

                        elif t == "done":
                            if speaking:
                                speaking = False
                                await client_ws.send(json.dumps({"type": "speaking", "state": "end"}))
                            full = " ".join(reply_buf).strip()
                            if full:
                                log.add_turn("ai", full)
                            reply_buf.clear()

                        elif t == "interrupted":
                            if speaking:
                                speaking = False
                                await client_ws.send(json.dumps({"type": "speaking", "state": "end"}))
                            reply_buf.clear()

                        elif t == "error":
                            await client_ws.send(msg)

            sei_task = asyncio.create_task(pump_sei())

            try:
                async for msg in client_ws:
                    if isinstance(msg, bytes):
                        for event, chunk in vad.feed(msg):
                            if event == "speech_start":
                                await sei_ws.send(json.dumps({"type": "speech_start"}))
                                if chunk:
                                    await sei_ws.send(chunk)
                            elif event == "speech_end":
                                await sei_ws.send(json.dumps({"type": "speech_end"}))
                            elif chunk:
                                await sei_ws.send(chunk)

                    elif isinstance(msg, str):
                        data = json.loads(msg)
                        t    = data.get("type")

                        if t == "barge_in":
                            await sei_ws.send(json.dumps({"type": "stop"}))

                        elif t == "transcript":
                            # Pre-transcribed text from client-side STT (e.g. laptop whisper.cpp)
                            text = data.get("text", "").strip()
                            if text:
                                log.add_turn("user", text)
                                await client_ws.send(json.dumps({"type": "transcript", "text": text}))
                                await sei_ws.send(json.dumps({"type": "speech_start"}))
                                await sei_ws.send(json.dumps({"type": "speech_end", "text": text}))

            finally:
                sei_task.cancel()
                try:
                    await sei_task
                except (asyncio.CancelledError, Exception):
                    pass

    except Exception as exc:
        print(f"[{tag}] error: {exc}", flush=True)
        try:
            await client_ws.send(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass

    finally:
        print(f"[{tag}] saving call log...", flush=True)
        await log.save_and_send()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    print(f"Voice Bridge on ws://{BIND_HOST}:{BIND_PORT}", flush=True)
    print(f"  sei_engine : {SEI_WS_URL}", flush=True)
    print(f"  openclaw   : {OPENCLAW_URL or '(local log only)'}", flush=True)
    print(f"  log dir    : {LOG_DIR}", flush=True)
    async with websockets.serve(handler, BIND_HOST, BIND_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
