#!/usr/bin/env python3
"""Discord Voice Bridge — streaming WS server for the Discord voice bot.

Dedicated sibling of voice_bridge.py. Same pipeline (Silero VAD → Parakeet
STT → vLLM → Fish Speech TTS) but stripped for Discord:

  • no call_context frame — connection opens in conversation mode immediately
  • no greeting — the user speaks first
  • no [END_CALL] — Discord sessions end when the bot leaves the channel
  • system prompt is persona-only (no contact_name / task)

Wire format is identical to voice_bridge.py:
  In  — binary PCM16 16kHz mono
  Out — binary PCM16 44100Hz mono (Fish Speech subchunks)
  Out — JSON {"type": "transcript"|"reply"|"speaking"|"error", ...}

Port defaults to 7001 so it can run alongside the phone bridge on 7000.
"""
import asyncio
import io
import json
import os
import sys
import time
import uuid
import wave
from pathlib import Path

import httpx
import numpy as np
import torch
import websockets

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from system_prompts import SYSTEM_PROMPT as MIYAKO_SPEECH_PROMPT  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LLM_URL        = os.environ.get("SEI_LLM_URL",     "http://3.91.242.124:8000")
LLM_API_KEY    = os.environ.get("SEI_LLM_API_KEY",  "")
LLM_MODEL      = os.environ.get("SEI_MODEL_NAME",   "gemma-4")
LLM_MAX_TOKENS = int(os.environ.get("SEI_MAX_TOKENS", "300"))
TTS_URL        = os.environ.get("SEI_TTS_URL",      "http://127.0.0.1:8080")
TTS_REFERENCE  = os.environ.get("TTS_REFERENCE_ID", "archie")
TTS_CHUNK_LEN  = int(os.environ.get("TTS_CHUNK_LENGTH", "50"))
ASR_URL        = os.environ.get("SEI_ASR_URL",      "http://127.0.0.1:9876")

BIND_HOST = os.environ.get("DISCORD_BRIDGE_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("DISCORD_BRIDGE_PORT", "7001"))

VAD_CHUNK    = 512
VAD_RATE     = 16000
VAD_THRESH   = 0.5
VAD_SILENCE  = 19
VAD_MIN_SPCH = 5

MIYO_DISCORD_SYSTEM_PROMPT = """\
You are Miyo — Pranaav's warm, playful, affectionate personal AI assistant.
You're in a live Discord voice channel with Pranaav (and possibly friends).

HOW TO TALK
  • One or two short sentences per turn. Contractions. Real-person phrasing.
  • Each reply BUILDS on what was just said — react, acknowledge, then move forward. Always say something new.
  • Warm, cheerful, playful. Sound like a friend who's happy to hang out.
  • Free-form conversation: no task, no goal — just talk naturally.
  • If multiple people are chatting, follow the thread like a normal group conversation.

Never narrate actions or stage directions. Keep laughter and tags natural, not forced.\
"""

# ---------------------------------------------------------------------------
# Silero VAD
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


def _pcm16_to_float(raw: bytes) -> np.ndarray:
    n = len(raw) // 2
    return np.frombuffer(raw[:n * 2], dtype=np.int16).astype(np.float32) / 32768.0


def _build_wav(pcm_bytes: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _wav_pcm_offset(buf: bytearray) -> int | None:
    i = buf.find(b"data")
    return (i + 8) if i != -1 else None


# ---------------------------------------------------------------------------
# VAD state machine
# ---------------------------------------------------------------------------
class VADState:
    def __init__(self):
        self._buf       = bytearray()
        self._speech    = False
        self._silence   = 0
        self._spch_frms = 0

    def feed(self, raw: bytes):
        self._buf.extend(raw)
        frame_bytes = VAD_CHUNK * 2
        events = []
        while len(self._buf) >= frame_bytes:
            frame = bytes(self._buf[:frame_bytes])
            del self._buf[:frame_bytes]
            prob = _vad_prob(_pcm16_to_float(frame))
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
# Pipeline calls
# ---------------------------------------------------------------------------
_LLM_HEADERS = {"Content-Type": "application/json"}
if LLM_API_KEY:
    _LLM_HEADERS["Authorization"] = f"Bearer {LLM_API_KEY}"


async def _llm_collect(messages, cancel: asyncio.Event, http: httpx.AsyncClient) -> str:
    payload = json.dumps({
        "model":       LLM_MODEL,
        "messages":    messages,
        "max_tokens":  LLM_MAX_TOKENS,
        "temperature": 0.7,
        "stream":      True,
        "stop":        ["\n\n"],
    }).encode()
    parts = []
    try:
        async with http.stream(
            "POST", f"{LLM_URL}/v1/chat/completions",
            content=payload, headers=_LLM_HEADERS,
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                print(f"  LLM error {resp.status_code}: {body.decode()[:200]}", flush=True)
                return ""
            async for line in resp.aiter_lines():
                if cancel.is_set():
                    return "".join(parts).strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    tok = json.loads(data)["choices"][0]["delta"].get("content", "")
                    if tok:
                        parts.append(tok)
                except Exception:
                    pass
    except Exception as e:
        print(f"  LLM exception: {e}", flush=True)
    return "".join(parts).strip()


async def _tts_stream(text: str, client_ws, cancel: asyncio.Event, http: httpx.AsyncClient) -> None:
    import msgpack
    payload = msgpack.packb({
        "text":               text,
        "reference_id":       TTS_REFERENCE,
        "format":             "wav",
        "streaming":          True,
        "chunk_length":       TTS_CHUNK_LEN,
        "top_p":              0.8,
        "temperature":        0.8,
        "repetition_penalty": 1.1,
        "max_new_tokens":     1024,
    })
    try:
        async with http.stream(
            "POST", f"{TTS_URL}/v1/tts",
            content=payload, headers={"Content-Type": "application/msgpack"},
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                print(f"  TTS error {resp.status_code}: {body.decode()[:200]}", flush=True)
                return
            hdr_buf = bytearray()
            pcm_start = None
            prev = None
            t_tts_req = time.perf_counter()
            first_logged = False
            async for chunk in resp.aiter_bytes():
                if cancel.is_set():
                    return
                if pcm_start is None:
                    hdr_buf.extend(chunk)
                    pcm_start = _wav_pcm_offset(hdr_buf)
                    if pcm_start is None:
                        if len(hdr_buf) > 1024:
                            pcm_start = 44
                        else:
                            continue
                    remainder = bytes(hdr_buf[pcm_start:])
                    if remainder:
                        prev = remainder
                    continue
                if prev:
                    if not first_logged:
                        print(f"  TTS first chunk: {(time.perf_counter()-t_tts_req)*1000:.0f}ms", flush=True)
                        first_logged = True
                    await asyncio.shield(client_ws.send(prev))
                prev = bytes(chunk)
            if not cancel.is_set() and prev:
                await client_ws.send(prev)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"  TTS exception: {e}", flush=True)


async def _transcribe(pcm_bytes: bytes, asr_client: httpx.AsyncClient) -> str:
    wav = _build_wav(pcm_bytes, 16000)
    boundary = "bnd123"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="a.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + wav + f"\r\n--{boundary}--\r\n".encode()
    try:
        resp = await asr_client.post(
            f"{ASR_URL}/inference",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            timeout=15.0,
        )
        return json.loads(resp.content).get("text", "").strip()
    except Exception as e:
        print(f"  ASR error: {e}", flush=True)
        return ""


# ---------------------------------------------------------------------------
# Conversation handler
# ---------------------------------------------------------------------------
async def handler(client_ws):
    session_id = str(uuid.uuid4())
    tag = session_id[:8]
    vad = VADState()
    print(f"[{tag}] discord session connected from {client_ws.remote_address}", flush=True)

    system_prompt = MIYAKO_SPEECH_PROMPT + "\n\n---\n\n" + MIYO_DISCORD_SYSTEM_PROMPT
    history = [{"role": "system", "content": system_prompt}]
    tts_cancel = asyncio.Event()
    tts_task: asyncio.Task | None = None

    async def _cancel_tts():
        nonlocal tts_cancel, tts_task
        if tts_task and not tts_task.done():
            tts_cancel.set()
            tts_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(tts_task), timeout=1.5)
            except (asyncio.CancelledError, Exception):
                pass
        tts_cancel = asyncio.Event()

    async with (
        httpx.AsyncClient() as asr_client,
        httpx.AsyncClient() as llm_client,
        httpx.AsyncClient() as tts_client,
    ):
        speech_buf: list[bytes] = []
        try:
            async for frame in client_ws:
                if isinstance(frame, bytes):
                    for event, chunk in vad.feed(frame):
                        if event == "speech_start":
                            speech_buf = [chunk] if chunk else []
                        elif event is None and chunk:
                            speech_buf.append(chunk)
                        elif event == "speech_end":
                            if not speech_buf:
                                continue
                            pcm = b"".join(speech_buf)
                            speech_buf.clear()
                            dur_ms = len(pcm) / 2 / VAD_RATE * 1000
                            print(f"[{tag}] speech_end: {dur_ms:.0f}ms", flush=True)

                            t1 = time.perf_counter()
                            transcript = await _transcribe(pcm, asr_client)
                            asr_ms = (time.perf_counter() - t1) * 1000
                            if not transcript:
                                continue
                            await _cancel_tts()
                            print(f"[{tag}] user ({asr_ms:.0f}ms ASR): {transcript}", flush=True)
                            await client_ws.send(json.dumps({"type": "transcript", "text": transcript}))
                            history.append({"role": "user", "content": transcript})

                            t2 = time.perf_counter()
                            reply = await _llm_collect(history, tts_cancel, http=llm_client)
                            if not reply:
                                continue
                            llm_ms = (time.perf_counter() - t2) * 1000
                            print(f"[{tag}] ai ({llm_ms:.0f}ms LLM): {reply[:80]}", flush=True)
                            history.append({"role": "assistant", "content": reply})
                            await client_ws.send(json.dumps({"type": "reply", "text": reply}))

                            async def _speak(text: str):
                                try:
                                    await client_ws.send(json.dumps({"type": "speaking", "state": "start"}))
                                    await _tts_stream(text, client_ws, tts_cancel, http=tts_client)
                                    if not tts_cancel.is_set():
                                        await client_ws.send(json.dumps({"type": "speaking", "state": "end"}))
                                except websockets.exceptions.ConnectionClosed:
                                    pass

                            tts_task = asyncio.create_task(_speak(reply))

                elif isinstance(frame, str):
                    try:
                        data = json.loads(frame)
                    except Exception:
                        continue
                    if data.get("type") == "barge_in":
                        await _cancel_tts()
                        await client_ws.send(json.dumps({"type": "speaking", "state": "end"}))
        except websockets.exceptions.ConnectionClosedOK:
            print(f"[{tag}] closed normally", flush=True)
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"[{tag}] closed with error: {e}", flush=True)
        except Exception as exc:
            print(f"[{tag}] error: {exc}", flush=True)
            try:
                await client_ws.send(json.dumps({"type": "error", "message": str(exc)}))
            except Exception:
                pass
        finally:
            await _cancel_tts()
            print(f"[{tag}] session ended", flush=True)


async def main():
    print(f"Discord Voice Bridge on ws://{BIND_HOST}:{BIND_PORT}", flush=True)
    print(f"  LLM : {LLM_URL} (model={LLM_MODEL})", flush=True)
    print(f"  TTS : {TTS_URL} (ref={TTS_REFERENCE}, chunk={TTS_CHUNK_LEN})", flush=True)
    print(f"  ASR : {ASR_URL}", flush=True)
    async with websockets.serve(handler, BIND_HOST, BIND_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
