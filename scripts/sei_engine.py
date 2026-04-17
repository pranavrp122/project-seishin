#!/usr/bin/env python3
"""Sei Engine - Async WebSocket server bridging clients to Gemma 4 LLM.

Streams LLM responses as sentence-boundary JSON frames over WebSocket.
Auth via Bearer token, single-session enforcement, conversation memory.

Usage:
    SEI_AUTH_TOKEN=your-secret python scripts/sei_engine.py
"""
import asyncio
import json
import os
import random
import re
import time
from http import HTTPStatus
from collections.abc import AsyncGenerator

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
import httpx
import ormsgpack

from system_prompts import SYSTEM_PROMPT, SEED_HISTORY

# --- Configuration ---
AUTH_TOKEN = os.environ.get("SEI_AUTH_TOKEN", "")
if not AUTH_TOKEN:
    if os.environ.get("SEI_DEV_MODE") == "1":
        AUTH_TOKEN = "test-token-change-me"
    else:
        import sys
        print("FATAL: SEI_AUTH_TOKEN not set. Export it or set SEI_DEV_MODE=1 for dev.", file=sys.stderr)
        sys.exit(1)
BIND_ADDR = os.environ.get("SEI_BIND", "127.0.0.1")
PORT = int(os.environ.get("SEI_PORT", "5052"))
LLM_URL = os.environ.get("SEI_LLM_URL", "http://127.0.0.1:8000")
MODEL_NAME = os.environ.get("SEI_MODEL_NAME", "gemma-4")
MAX_TOKENS = int(os.environ.get("SEI_MAX_TOKENS", "300"))
TEMPERATURE = float(os.environ.get("SEI_TEMPERATURE", "0.7"))
REPETITION_PENALTY = float(os.environ.get("SEI_REPETITION_PENALTY", "1.3"))

TTS_URL = os.environ.get("SEI_TTS_URL", "http://127.0.0.1:8080")
TTS_REFERENCE_ID = os.environ.get("TTS_REFERENCE_ID", "archie")
TTS_CHUNK_LENGTH = int(os.environ.get("TTS_CHUNK_LENGTH", "200"))
TTS_TOP_P = float(os.environ.get("TTS_TOP_P", "0.8"))
TTS_TEMPERATURE = float(os.environ.get("TTS_TEMPERATURE", "0.8"))
TTS_REPETITION_PENALTY_TTS = float(os.environ.get("TTS_REPETITION_PENALTY", "1.1"))
TTS_MAX_NEW_TOKENS = int(os.environ.get("TTS_MAX_NEW_TOKENS", "1024"))
WAV_HEADER_SIZE = 44  # Fallback if data chunk parsing fails

ASR_URL = os.environ.get("SEI_ASR_URL", "http://127.0.0.1:9876")

REPORT_API_URL = os.environ.get("REPORT_API_URL", "http://127.0.0.1:9000")
REPORT_API_KEY = os.environ.get("REPORT_API_KEY", "")

# --- Report intent detection ---
# Permissive: any mention of report / dashboard / tableau / analytics / metrics
# triggers an LLM review; false positives are handled gracefully in the prompt.
_REPORT_PREFIX = re.compile(r"^\s*(?:nexus\s+)?report\s*[:,-]?\s+", re.IGNORECASE)
# Broad prefilter: reports/dashboards/analytics terms, common business entities,
# and data-query starters. The LLM then decides if it's actually a data request.
_REPORT_TOPIC = re.compile(
    r"\b("
    r"reports?|dashboards?|tableau|analytics|metrics?|kpis?|"
    r"customers?|orders?|products?|employees?|suppliers?|invoices?|"
    r"inventory|warehouses?|sales|revenue|profits?|margins?|payments?|"
    r"transactions?|campaigns?|refunds?|returns?|shipments?|"
    r"how\s+many|how\s+much|what\s+(is|are|was|were)\s+(?:our|the)|"
    r"total\s+\w+|average\s+\w+|top\s+\d"
    r")\b",
    re.IGNORECASE,
)
_REPORT_PROGRESS_MSGS = [
    "Still working on it, shouldn't be too much longer now.",
    "Almost there, just pulling the final numbers together.",
    "Taking a bit longer than usual but nearly done, hang on.",
    "Still running, this one's a heavy one. Almost got it.",
]


def _is_report_request(text: str) -> bool:
    t = (text or "").strip()
    return bool(_REPORT_PREFIX.search(t) or _REPORT_TOPIC.search(t))


async def classify_yes_no(text: str, context: str) -> bool:
    """Use the LLM as a fast binary classifier. Returns True for YES, False otherwise.

    `context` describes the question the user was just asked.
    On any error or ambiguous output, returns False (safe default: don't run reports).
    """
    system = (
        "You are a binary intent classifier. "
        "Given the context and user response, reply with a single word: YES or NO. "
        "No punctuation, no explanation."
    )
    user_msg = f"Context: {context}\nUser response: {text}\nAnswer (YES or NO):"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{LLM_URL}/v1/chat/completions",
                json={
                    "model": MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 4,
                    "temperature": 0.0,
                    "stream": False,
                },
                timeout=httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0),
            )
            resp.raise_for_status()
            out = resp.json()["choices"][0]["message"]["content"].strip().upper()
            result = out.startswith("YES") or " YES" in f" {out}"
            print(f"  classify_yes_no('{text[:40]}') -> {out!r} => {result}")
            return result
    except Exception as e:
        print(f"  classify_yes_no failed: {e}")
        return False


_REPORT_LEADINS = [
    "[happy] Alright, here's what I found. ",
    "[calm] Got your results. ",
    "[happy] Here you go — ",
    "[calm] Done, here's what came back. ",
    "[happy] Alright, got it. ",
]

async def deliver_report_result(websocket, report_task: asyncio.Task, history: list, tts_client: httpx.AsyncClient, query: str = "") -> None:
    """Speak Claude's verbatim summary and push a report_log frame to the client."""
    try:
        res = report_task.result()
        raw_summary = (res.get("summary") or "").strip()
    except Exception as _e:
        print(f"  Report API error: {_e}")
        res = {}
        raw_summary = ""

    # Send report_log frame so the client can display SQL + raw data in the Log tab
    await websocket.send(json.dumps({
        "type": "report_log",
        "query": query,
        "sql": res.get("sql") or res.get("sql_text") or "",
        "row_count": res.get("row_count", 0),
        "results": res.get("results", []),
        "summary": raw_summary,
        "claude_interactions": res.get("claude_interactions", []),
    }))

    if raw_summary:
        spoken = random.choice(_REPORT_LEADINS) + raw_summary
    else:
        spoken = "[calm] Sorry, I ran into an issue pulling that report. Want me to try again?"

    history.append({"role": "assistant", "content": spoken})
    await websocket.send(json.dumps({"type": "sentence", "text": spoken}))
    _ce = asyncio.Event()
    await tts_full_response(websocket, spoken, tts_client, _ce)
    await websocket.send(json.dumps({"type": "done"}))


async def call_report_api(user_request: str) -> dict:
    """POST user request to the report generator and return the response dict."""
    headers = {"X-API-Key": REPORT_API_KEY} if REPORT_API_KEY else {}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{REPORT_API_URL}/report",
            json={"user_request": user_request},
            headers=headers,
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
        )
        resp.raise_for_status()
        return resp.json()


def pcm16_to_wav(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    """Wrap raw PCM16 mono data in a WAV header."""
    import struct
    data_size = len(pcm_data)
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b'data', data_size,
    )
    return header + pcm_data


def find_wav_data_offset(buf: bytes) -> int | None:
    """Find byte offset where PCM audio data starts in a WAV buffer.

    Parses RIFF/WAV subchunks to locate the 'data' chunk instead of
    assuming a fixed 44-byte header (Fish Speech may add extra chunks).
    Returns offset into buf, or None if not enough data accumulated yet.
    Returns 0 if the buffer is not a WAV file (stream as-is).
    """
    if len(buf) < 12:
        return None
    if buf[:4] != b'RIFF' or buf[8:12] != b'WAVE':
        return 0
    pos = 12
    while pos + 8 <= len(buf):
        chunk_id = buf[pos:pos + 4]
        chunk_size = int.from_bytes(buf[pos + 4:pos + 8], 'little')
        if chunk_id == b'data':
            return pos + 8
        pos += 8 + chunk_size
        if chunk_size % 2 != 0:
            pos += 1  # WAV chunks are word-aligned
    return None

def fade_out_pcm(pcm: bytes, fade_ms: int = 200, sample_rate: int = 44100) -> bytes:
    """Apply linear fade-out to the last fade_ms ms of PCM16 mono audio."""
    import struct
    if len(pcm) < 4:
        return pcm
    fade_samples = sample_rate * fade_ms // 1000
    n = len(pcm) // 2
    samples = list(struct.unpack(f'<{n}h', pcm[:n * 2]))
    start = max(0, n - fade_samples)
    total = n - start
    for i in range(start, n):
        factor = 1.0 - (i - start) / total
        samples[i] = int(samples[i] * factor)
    return struct.pack(f'<{n}h', *samples) + pcm[n * 2:]


# --- Global state ---
active_ws = None


async def process_request(connection, request):
    """Validate Bearer token and enforce single session before WebSocket upgrade."""
    global active_ws
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {AUTH_TOKEN}":
        return connection.respond(HTTPStatus.UNAUTHORIZED, "Invalid token\n")
    if active_ws is not None:
        return connection.respond(HTTPStatus.SERVICE_UNAVAILABLE, "Session already active\n")


def build_initial_messages() -> list[dict]:
    """Build the starting messages array with system prompt and seed history."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, text in SEED_HISTORY:
        messages.append({
            "role": "user" if role == "User" else "assistant",
            "content": text,
        })
    return messages


def is_quality_response(reply: str) -> bool:
    """Check if LLM reply meets minimum quality bar."""
    return bool(reply) and len(reply) >= 10


async def tts_full_response(ws, text: str, tts_client: httpx.AsyncClient, cancel_event: asyncio.Event):
    """Send full LLM response to Fish Speech TTS and stream PCM audio back.

    Fish Speech streams audio chunks back via streaming=True.
    """
    tts_text = text
    if not tts_text.strip():
        return

    payload = ormsgpack.packb({
        "text": tts_text,
        "reference_id": TTS_REFERENCE_ID,
        "format": "wav",
        "streaming": True,
        "chunk_length": TTS_CHUNK_LENGTH,
        "top_p": TTS_TOP_P,
        "temperature": TTS_TEMPERATURE,
        "repetition_penalty": TTS_REPETITION_PENALTY_TTS,
        "max_new_tokens": TTS_MAX_NEW_TOKENS,
    })

    try:
        async with tts_client.stream(
            "POST", f"{TTS_URL}/v1/tts",
            content=payload,
            headers={"Content-Type": "application/msgpack"},
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                print(f"  TTS error: {response.status_code}: {body.decode()}")
                try:
                    await ws.send(json.dumps({"type": "error", "message": "TTS error"}))
                except ConnectionClosed:
                    pass
                return

            header_buf = bytearray()
            data_offset = None
            prev_chunk = None
            async for chunk in response.aiter_bytes():
                if cancel_event.is_set():
                    return
                if data_offset is None:
                    header_buf.extend(chunk)
                    data_offset = find_wav_data_offset(header_buf)
                    if data_offset is None:
                        if len(header_buf) > 1024:
                            data_offset = WAV_HEADER_SIZE
                            remainder = bytes(header_buf[data_offset:])
                            if remainder:
                                prev_chunk = remainder
                        continue
                    remainder = bytes(header_buf[data_offset:])
                    if remainder:
                        prev_chunk = remainder
                    continue
                # Send previous chunk, buffer current
                if prev_chunk:
                    await ws.send(prev_chunk)
                prev_chunk = bytes(chunk)

            # Send final chunk with fade-out applied, then silence padding
            if not cancel_event.is_set() and prev_chunk:
                await ws.send(fade_out_pcm(prev_chunk))
                await ws.send(bytes(44100 * 150 // 1000 * 2))
    except httpx.ConnectError:
        print(f"  TTS connection failed: {TTS_URL}")
        try:
            await ws.send(json.dumps({"type": "error", "message": "TTS service unavailable"}))
        except ConnectionClosed:
            pass
    except Exception as e:
        print(f"  TTS error: {e}")
        try:
            await ws.send(json.dumps({"type": "error", "message": "TTS error"}))
        except ConnectionClosed:
            pass


async def stream_llm(messages: list[dict], cancel_event: asyncio.Event) -> AsyncGenerator[str, None]:
    """Stream tokens from vLLM chat completions endpoint."""
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{LLM_URL}/v1/chat/completions",
            json={
                "model": MODEL_NAME,
                "messages": messages,
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
                "repetition_penalty": REPETITION_PENALTY,
                "stream": True,
                "stop": ["\n\n"],
            },
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
        ) as response:
            if response.status_code != 200:
                text = await response.aread()
                raise RuntimeError(f"LLM returned {response.status_code}: {text.decode()}")
            async for line in response.aiter_lines():
                if cancel_event.is_set():
                    return
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    content = chunk["choices"][0]["delta"].get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


async def handle_llm_response(ws, messages: list[dict], tts_client: httpx.AsyncClient, cancel_event: asyncio.Event) -> str:
    """Stream LLM tokens, collect full response, then send to UI and TTS."""
    reply_parts = []
    t0 = time.perf_counter()
    first_token = True

    async for token in stream_llm(messages, cancel_event):
        if first_token:
            ttft = (time.perf_counter() - t0) * 1000
            print(f"  TTFT: {ttft:.0f}ms", flush=True)
            first_token = False
        reply_parts.append(token)
        if cancel_event.is_set():
            break

    full_reply = "".join(reply_parts).strip()

    if cancel_event.is_set():
        await ws.send(json.dumps({"type": "interrupted"}))
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"  Interrupted at {elapsed:.0f}ms", flush=True)
        return full_reply

    if full_reply:
        llm_done = (time.perf_counter() - t0) * 1000
        print(f"  LLM done: {llm_done:.0f}ms, sending to UI+TTS ({len(full_reply)} chars)", flush=True)
        await ws.send(json.dumps({"type": "sentence", "text": full_reply}))
        await tts_full_response(ws, full_reply, tts_client, cancel_event)

    if cancel_event.is_set():
        await ws.send(json.dumps({"type": "interrupted"}))
    else:
        await ws.send(json.dumps({"type": "done"}))
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"  Total: {elapsed:.0f}ms", flush=True)

    return full_reply


async def transcribe_audio(wav_bytes: bytes, asr_client: httpx.AsyncClient, label: str = "ASR") -> str:
    """Send WAV audio to whisper-server and return transcribed text."""
    t0 = time.perf_counter()
    try:
        resp = await asr_client.post(
            f"{ASR_URL}/inference",
            files={"file": ("audio.wav", wav_bytes, "audio/wav")},
            data={
                "response_format": "json",
                "language": "en",
                "temperature": "0.2",           # small stochasticity helps short clips
                "no_speech_thold": "0.3",       # default 0.6; lower = more forgiving
                "logprob_thold": "-1.5",        # default -1.0; lower = keep weaker tokens
            },
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0),
        )
        if resp.status_code != 200:
            print(f"  {label} error: {resp.status_code}: {resp.text}")
            return ""
        text = resp.json().get("text", "").strip()
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"  {label}: {elapsed:.0f}ms -> '{text[:60]}'", flush=True)
        return text
    except Exception as e:
        print(f"  {label} error: {e}")
        return ""


async def live_transcribe(audio_buf: bytearray, result: dict, stop: asyncio.Event, asr_client: httpx.AsyncClient):
    """Background: run whisper on accumulated audio every ~1s of new data.

    By the time speech_end arrives, a recent transcript is already cached.
    """
    last_len = 0
    min_new = 16000 * 2  # 1 second of 16kHz PCM16 = 32000 bytes
    run = 0
    while not stop.is_set():
        await asyncio.sleep(0.3)
        if stop.is_set():
            break
        cur_len = len(audio_buf)
        if cur_len - last_len < min_new:
            continue
        run += 1
        wav = pcm16_to_wav(bytes(audio_buf[:cur_len]))
        text = await transcribe_audio(wav, asr_client, label=f"ASR-live#{run}")
        if text:
            result["text"] = text
            result["len"] = cur_len
        last_len = cur_len


async def handler(websocket):
    """Handle a single WebSocket client session with barge-in support."""
    global active_ws
    active_ws = websocket  # Set here where finally block guarantees cleanup
    history = build_initial_messages()
    print(f"Client connected: {websocket.remote_address}")

    try:
        async with httpx.AsyncClient() as tts_client:
            pending_msg = None  # Buffered message from stop-listener
            pending_report_request = None  # Request restated and awaiting user yes/no
            active_report_task = None   # Background asyncio.Task for call_report_api
            active_report_query = ""    # The original user query being reported on
            _report_progress_idx = 0    # Index into _REPORT_PROGRESS_MSGS
            audio_buf = bytearray()  # Streaming PCM accumulation buffer
            is_accumulating = False
            asr_task = None
            asr_stop = None
            asr_result = {"text": "", "len": 0}

            while True:
                # --- Phase A: Wait for user message ---
                if pending_msg:
                    msg = pending_msg
                    pending_msg = None
                else:
                    try:
                        if active_report_task is not None:
                            raw = await asyncio.wait_for(websocket.recv(), timeout=8.0)
                        else:
                            raw = await websocket.recv()
                    except ConnectionClosed:
                        break
                    except asyncio.TimeoutError:
                        # Silence while report is running — deliver result or send update
                        if active_report_task.done():
                            await deliver_report_result(websocket, active_report_task, history, tts_client, active_report_query)
                            active_report_task = None
                            active_report_query = ""
                        else:
                            update = _REPORT_PROGRESS_MSGS[_report_progress_idx] \
                                if _report_progress_idx < len(_REPORT_PROGRESS_MSGS) \
                                else "Still on it, just a bit longer."
                            _report_progress_idx += 1
                            await websocket.send(json.dumps({"type": "sentence", "text": update}))
                            _ce = asyncio.Event()
                            await tts_full_response(websocket, update, tts_client, _ce)
                            await websocket.send(json.dumps({"type": "done"}))
                        continue

                    # Binary frame: streaming PCM chunk or legacy full WAV
                    if isinstance(raw, bytes):
                        if is_accumulating:
                            audio_buf.extend(raw)
                            continue
                        # Legacy: full WAV sent in one frame
                        text = await transcribe_audio(raw, tts_client)
                        if text:
                            msg = {"type": "message", "text": text}
                            await websocket.send(json.dumps({"type": "transcript", "text": text}))
                        else:
                            continue
                    else:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                            continue

                    # Handle streaming audio control messages
                    if msg.get("type") == "speech_start":
                        audio_buf.clear()
                        is_accumulating = True
                        asr_result = {"text": "", "len": 0}
                        asr_stop = asyncio.Event()
                        asr_task = asyncio.create_task(
                            live_transcribe(audio_buf, asr_result, asr_stop, tts_client)
                        )
                        continue
                    if msg.get("type") == "speech_end":
                        is_accumulating = False
                        # Cancel background transcription (don't wait for in-flight whisper)
                        if asr_stop:
                            asr_stop.set()
                        if asr_task:
                            asr_task.cancel()
                            try:
                                await asr_task
                            except asyncio.CancelledError:
                                pass
                            asr_task = None
                        if audio_buf:
                            if asr_result["text"]:
                                # Live transcription already has a result — use it instantly
                                text = asr_result["text"]
                                skip_pct = 100 * (1 - asr_result["len"] / len(audio_buf))
                                print(f"  ASR-cached: '{text[:60]}' (tail {skip_pct:.0f}% unprocessed)", flush=True)
                            else:
                                # Short utterance, no live result yet — final pass
                                wav = pcm16_to_wav(bytes(audio_buf))
                                text = await transcribe_audio(wav, tts_client, label="ASR-final")
                            audio_buf.clear()
                            if text:
                                msg = {"type": "message", "text": text}
                                await websocket.send(json.dumps({"type": "transcript", "text": text}))
                            else:
                                continue
                        else:
                            continue

                if msg.get("type") != "message" or not msg.get("text"):
                    if msg.get("type") not in ("speech_start", "speech_end", "stop"):
                        await websocket.send(json.dumps({"type": "error", "message": "Expected {type: message, text: ...}"}))
                    continue

                user_text = msg["text"].strip()
                if not user_text:
                    continue

                history.append({"role": "user", "content": user_text})
                print(f"  User: {user_text}")

                # --- Report intent routing ---
                # Pending verification: user had a report restated and we're waiting on yes/no
                if pending_report_request is not None:
                    confirmed = await classify_yes_no(
                        user_text,
                        f"Miyako just restated this report request and asked the user to confirm: {pending_report_request}",
                    )
                    if confirmed:
                        print(f"  Report confirmed: {pending_report_request[:80]}")
                        active_report_query = pending_report_request
                        active_report_task = asyncio.create_task(call_report_api(pending_report_request))
                        _report_progress_idx = 0
                        _ack_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                "[INTERNAL: User confirmed. You are now pulling the data in the background. "
                                "Short one-sentence ack. Vary your phrasing.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        ack_reply = await handle_llm_response(websocket, _ack_messages, tts_client, _ce)
                        if ack_reply:
                            history.append({"role": "assistant", "content": ack_reply})
                        pending_report_request = None
                        continue
                    else:
                        # Not a yes — drop pending and let the current message route normally
                        # (if it's a rephrased report, _is_report_request will catch it below)
                        print(f"  Report NOT confirmed; dropping pending.")
                        pending_report_request = None

                # New report intent: restate and ask for confirmation, DO NOT fire yet
                if _is_report_request(user_text):
                    pending_report_request = user_text
                    _confirm_messages = list(history[:-1]) + [{
                        "role": "user",
                        "content": (
                            f"{user_text}\n\n"
                            "[INTERNAL: User asked for a data report. Briefly restate what you heard in one short sentence "
                            "and end with a yes/no check (e.g. 'sound right?'). "
                            "Do NOT ask what extra fields to include, do NOT offer alternatives, "
                            "do NOT offer to add stats — just verify the request. Confirmation only, do not start running it.]"
                        ),
                    }]
                    _ce = asyncio.Event()
                    confirm_reply = await handle_llm_response(websocket, _confirm_messages, tts_client, _ce)
                    if confirm_reply:
                        history.append({"role": "assistant", "content": confirm_reply})
                    continue

                # --- Phase B: Concurrent generation + stop listener ---
                cancel_event = asyncio.Event()

                gen_task = asyncio.create_task(
                    handle_llm_response(websocket, history, tts_client, cancel_event)
                )

                stop_result = {"new_msg": None}

                async def listen_for_stop():
                    """Listen for stop or new message during generation. Owns recv()."""
                    bargein_buf = bytearray()
                    bargein_accumulating = False
                    while True:
                        try:
                            raw = await websocket.recv()
                        except ConnectionClosed:
                            cancel_event.set()
                            return
                        # Binary frame during generation = streaming barge-in audio
                        if isinstance(raw, bytes):
                            if bargein_accumulating:
                                bargein_buf.extend(raw)
                            # Legacy: full WAV barge-in
                            else:
                                text = await transcribe_audio(raw, tts_client)
                                if text:
                                    cancel_event.set()
                                    await websocket.send(json.dumps({"type": "transcript", "text": text}))
                                    stop_result["new_msg"] = {"type": "message", "text": text}
                                return
                            continue
                        try:
                            parsed = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if parsed.get("type") == "stop":
                            cancel_event.set()
                            return
                        elif parsed.get("type") == "speech_start":
                            cancel_event.set()  # Interrupt immediately on speech
                            bargein_buf.clear()
                            bargein_accumulating = True
                        elif parsed.get("type") == "speech_end":
                            bargein_accumulating = False
                            if bargein_buf:
                                wav = pcm16_to_wav(bytes(bargein_buf))
                                text = await transcribe_audio(wav, tts_client)
                                if text:
                                    await websocket.send(json.dumps({"type": "transcript", "text": text}))
                                    stop_result["new_msg"] = {"type": "message", "text": text}
                            return
                        elif parsed.get("type") == "message" and parsed.get("text"):
                            cancel_event.set()
                            stop_result["new_msg"] = parsed
                            return

                listener_task = asyncio.create_task(listen_for_stop())

                # Wait for generation to finish OR stop signal
                done, pending = await asyncio.wait(
                    {gen_task, listener_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # --- Phase C: Cleanup ---
                # Only cancel listener (safe: just blocking on recv).
                # NEVER cancel gen_task — it uses cooperative cancellation
                # via cancel_event and must finish sending interrupted/done frame.
                if listener_task not in done:
                    listener_task.cancel()
                    try:
                        await listener_task
                    except asyncio.CancelledError:
                        pass

                # Wait for gen_task to finish (fast: cancel_event is set)
                if gen_task not in done:
                    try:
                        await gen_task
                    except asyncio.CancelledError:
                        pass

                # Get generation result
                try:
                    reply = gen_task.result()
                except Exception as e:
                    print(f"  LLM error: {e}")
                    await websocket.send(json.dumps({"type": "error", "message": "Generation failed"}))
                    history.pop()  # Remove the user message that caused the error
                    continue

                # --- Phase D: Update history ---
                interrupted = cancel_event.is_set()
                if interrupted:
                    if reply:
                        history.append({"role": "assistant", "content": reply})
                    print(f"  Interrupted. Partial reply: {reply[:80]}..." if reply else "  Interrupted. No partial reply.")
                else:
                    if is_quality_response(reply):
                        history.append({"role": "assistant", "content": reply})
                    else:
                        history.pop()  # Remove user message if response was low quality

                # Buffer new message from listener if one arrived
                if stop_result["new_msg"]:
                    pending_msg = stop_result["new_msg"]

                # Deliver report result only when the current turn finished cleanly (not interrupted).
                # If interrupted, the result will surface on next silence or next clean turn.
                if active_report_task is not None and active_report_task.done() and not interrupted:
                    await deliver_report_result(websocket, active_report_task, history, tts_client, active_report_query)
                    active_report_task = None
                    active_report_query = ""
    finally:
        active_ws = None
        print(f"Client disconnected: {websocket.remote_address}")


async def main():
    print(f"Sei Engine listening on {BIND_ADDR}:{PORT}")
    print(f"LLM: {LLM_URL} (model: {MODEL_NAME})")
    print(f"TTS: {TTS_URL} (reference: {TTS_REFERENCE_ID})")
    print(f"Auth: {'<from env>' if os.environ.get('SEI_AUTH_TOKEN') else '<dev mode>'}")
    async with serve(handler, BIND_ADDR, PORT, process_request=process_request) as server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSei Engine stopped.")
