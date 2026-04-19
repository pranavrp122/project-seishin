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
import time
from http import HTTPStatus
from collections import defaultdict
from collections.abc import AsyncGenerator

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
import httpx
import ormsgpack

import re

from system_prompts import SYSTEM_PROMPT, SEED_HISTORY, build_cache_summary_block
from intent_classifier import classify_intent
from session_cache import SessionCache
from op_spec import generate_op_spec
from cache_executor import CacheExecutor, _fuzzy_match_column
from text_utils import _normalize_datetime

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
LLM_API_KEY = os.environ.get("SEI_LLM_API_KEY", "")
_LLM_HEADERS = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
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

# Text mode: skip TTS entirely, responses show as text only
TEXT_MODE = os.environ.get("SEI_TEXT_MODE", "0") == "1"

async def handle_llm_response_text_only(ws, messages: list[dict], cancel_event: asyncio.Event) -> str:
    """Get full LLM response text without sending to WebSocket/TTS. For internal use."""
    reply_parts = []
    async for token in stream_llm(messages, cancel_event):
        reply_parts.append(token)
        if cancel_event.is_set():
            break
    return "".join(reply_parts).strip()


async def deliver_report_result(websocket, report_task: asyncio.Task, history: list, tts_client: httpx.AsyncClient, query: str = "", session_cache=None) -> bool:
    """Speak Claude's verbatim summary and push a report_log frame to the client."""
    try:
        res = report_task.result()
        raw_summary = (res.get("summary") or "").strip()
    except Exception as _e:
        print(f"  Report API error: {_e}")
        res = {}
        raw_summary = ""

    # Read the dashboard PNG from disk if the report generator produced one,
    # and inline as base64 so the client (over WebSocket) can render it without
    # a second HTTP fetch into the report generator's ports.
    import base64
    dashboard_b64 = ""
    report_path = res.get("report_path") or ""
    if report_path:
        try:
            with open(report_path, "rb") as fh:
                dashboard_b64 = base64.b64encode(fh.read()).decode("ascii")
        except Exception as _e:
            print(f"  could not read dashboard image: {_e}")

    # Send report_log frame so the client can display all pipeline artifacts in the Log tab
    await websocket.send(json.dumps({
        "type": "report_log",
        "query": query,
        "sql": res.get("sql") or res.get("sql_text") or "",
        "row_count": res.get("row_count", 0),
        "results": res.get("results", []),
        "summary": raw_summary,
        "claude_interactions": res.get("claude_interactions", []),
        "dashboard_b64": dashboard_b64,
    }))

    # Cache report data for follow-up operations
    if session_cache is not None and res.get("results"):
        report_id = session_cache.store(res, query=query, sql=res.get("sql") or res.get("sql_text") or "")
        print(f"  Cached report {report_id} ({len(res.get('results', []))} rows)")

    if raw_summary:
        # Embed both the summary and the actual rows so Gemma speaks only from real data
        rows_preview = json.dumps(res.get("results", [])[:10], default=str)[:600]
        intro_messages = list(history) + [{
            "role": "user",
            "content": (
                f"[INTERNAL: Data pull complete. Summary: {raw_summary}\n\n"
                f"Actual data ({res.get('row_count', 0)} rows, first 10):\n{rows_preview}\n\n"
                "IMPORTANT: Speak ONLY from the data above. Do not use memory or guess. "
                "Present naturally, 2-3 sentences max. Use exact values from the data.]"
            ),
        }]
        _ce = asyncio.Event()
        spoken = await handle_llm_response_text_only(websocket, intro_messages, _ce)
        if not spoken:
            spoken = raw_summary  # Fallback: just read the summary
    else:
        # Error case — LLM-generated in character
        error_messages = list(history) + [{
            "role": "user",
            "content": (
                "[INTERNAL: The data pull failed or returned no results. "
                "Let the user know naturally — offer to try again. Stay in character.]"
            ),
        }]
        _ce = asyncio.Event()
        spoken = await handle_llm_response_text_only(websocket, error_messages, _ce)
        if not spoken:
            spoken = "[calm] Hmm, something went wrong pulling that up. Want me to try again?"

    history.append({"role": "assistant", "content": spoken})
    await websocket.send(json.dumps({"type": "sentence", "text": spoken}))
    _ce = asyncio.Event()
    await tts_full_response(websocket, spoken, tts_client, _ce)
    await websocket.send(json.dumps({"type": "done"}))
    return True  # Signal successful delivery


async def call_report_api(user_request: str) -> dict:
    """POST user request to the report generator and return the response dict."""
    user_request = user_request[:1000]
    headers = {"X-API-Key": REPORT_API_KEY} if REPORT_API_KEY else {}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{REPORT_API_URL}/report",
            json={"user_request": user_request},
            headers=headers,
            timeout=httpx.Timeout(connect=5.0, read=240.0, write=5.0, pool=5.0),
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


# --- Rate limiting ---
_rate_limit_window: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_SECONDS = 60

# --- Global state ---
active_ws = None


async def process_request(connection, request):
    """Validate Bearer token and enforce single session before WebSocket upgrade."""
    global active_ws

    # Per-IP sliding window rate limit
    ip = connection.remote_address[0]
    now = time.time()
    window = _rate_limit_window[ip]
    _rate_limit_window[ip] = [t for t in window if now - t < _RATE_LIMIT_SECONDS]
    _rate_limit_window[ip].append(now)
    if len(_rate_limit_window[ip]) > _RATE_LIMIT_MAX:
        return connection.respond(HTTPStatus.TOO_MANY_REQUESTS, "Rate limit exceeded\n")

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
    In TEXT_MODE, skips TTS entirely — text is already sent as sentence frames.
    """
    if TEXT_MODE:
        return
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
            headers=_LLM_HEADERS,
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


async def _apply_op_chain(websocket, intent_result: dict, session_cache, report_query: str) -> None:
    """Auto-apply op_chain operations from a compound request after report delivery (D-05)."""
    chain = intent_result.get("op_chain")
    if not chain:
        return
    executor_instance = CacheExecutor()
    for chain_op in chain:
        target = session_cache.get_latest()
        if not target:
            break
        col = chain_op.get("column")
        if col and col not in target["columns"]:
            matched = _fuzzy_match_column(col, list(target["columns"].keys()))
            if matched:
                chain_op["column"] = matched
        chain_op.setdefault("explanation", "auto-chained operation")
        try:
            chain_result = executor_instance.execute(chain_op, target)
            session_cache.store({"results": chain_result["rows"]}, query=report_query, sql=target["sql"])
            await websocket.send(json.dumps({
                "type": "report_log",
                "query": report_query,
                "sql": target["sql"],
                "row_count": chain_result["row_count"],
                "results": chain_result["rows"],
                "summary": "",
                "claude_interactions": [],
                "dashboard_b64": "",
            }))
        except Exception as ce:
            print(f"  Op chain error: {ce}")


def _suggest_broadened_spec(op_spec: dict, report_data: dict) -> dict | None:
    """Generate a broadened version of a filter that returned zero results (D-07)."""
    if op_spec.get("op_type") != "filter":
        return None
    broadened = dict(op_spec)
    op = op_spec.get("operator")
    val = op_spec.get("value")

    if op == "eq" and val is not None:
        broadened["operator"] = "contains"
        return broadened

    if op in ("gt", "gte", "lt", "lte") and isinstance(val, (int, float)):
        delta = max(abs(val) * 0.2, 1)  # 20% of abs value, minimum delta of 1
        if op in ("gt", "gte"):
            broadened["value"] = val - delta  # Lower threshold to broaden
        else:
            broadened["value"] = val + delta  # Raise threshold to broaden
        return broadened

    return None


async def handler(websocket):
    """Handle a single WebSocket client session with barge-in support."""
    global active_ws
    active_ws = websocket  # Set here where finally block guarantees cleanup
    history = build_initial_messages()
    session_cache = SessionCache(ttl_seconds=600)
    print(f"Client connected: {websocket.remote_address}")

    try:
        async with httpx.AsyncClient() as tts_client:
            pending_msg = None  # Buffered message from stop-listener
            pending_overlap_query = None  # Held query awaiting user confirmation
            active_report_task = None   # Background asyncio.Task for call_report_api
            active_report_query = ""    # The original user query being reported on
            audio_buf = bytearray()  # Streaming PCM accumulation buffer
            is_accumulating = False
            asr_task = None
            asr_stop = None
            asr_result = {"text": "", "len": 0}
            undo_stack: list[dict] = []  # D-03: last 5 ops, each: {report_id, op_spec, pre_op_report_id, query_text}
            pending_suggestion_spec: dict | None = None  # D-07: broadened filter awaiting confirm
            last_intent_result: dict | None = None  # D-05: stored for op_chain after delivery
            _last_tracked_task = None  # Track task identity to reset progress flag on new task
            _progress_sent = False     # Only send one "still working" per report task

            while True:
                # --- Phase A: Wait for user message ---
                if pending_msg:
                    msg = pending_msg
                    pending_msg = None
                else:
                    try:
                        if active_report_task is not None:
                            # Auto-reset progress flag when task identity changes
                            if active_report_task is not _last_tracked_task:
                                _progress_sent = False
                                _last_tracked_task = active_report_task
                            raw = await asyncio.wait_for(websocket.recv(), timeout=20.0)
                        else:
                            raw = await websocket.recv()
                    except ConnectionClosed:
                        break
                    except asyncio.TimeoutError:
                        # 20s silence while report runs — deliver result or send one update max
                        if active_report_task.done():
                            await deliver_report_result(websocket, active_report_task, history, tts_client, active_report_query, session_cache=session_cache)
                            if last_intent_result:
                                await _apply_op_chain(websocket, last_intent_result, session_cache, active_report_query)
                                last_intent_result = None
                            active_report_task = None
                            active_report_query = ""
                            _last_tracked_task = None
                            _progress_sent = False
                        elif not _progress_sent:
                            await websocket.send(json.dumps({"type": "sentence", "text": "Still working on it..."}))
                            await websocket.send(json.dumps({"type": "done"}))
                            _progress_sent = True
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

                # D-08: Normalize relative date references before any classification
                user_text = _normalize_datetime(user_text)

                # --- Overlap confirmation handling ---
                skip_classification = False
                speculative_op_task = None

                if pending_overlap_query is not None:
                    overlap_intent = await classify_intent(user_text, history, bool(session_cache.all_reports()))
                    if overlap_intent["intent"] == "confirm":
                        pending_overlap_query = None
                        history.append({"role": "user", "content": user_text})
                        print(f"  User confirmed overlap -> follow_up_on_previous")
                        intent = "follow_up_on_previous"
                        confidence = 0.95
                        data_query = None
                        speculative_op_task = asyncio.create_task(
                            generate_op_spec(user_text, session_cache.summary(), session_cache.get_latest())
                        )
                        skip_classification = True
                    else:
                        saved_query = pending_overlap_query
                        pending_overlap_query = None
                        active_report_query = saved_query
                        active_report_task = asyncio.create_task(call_report_api(saved_query))
                        # Fall through to normal intent classification for current message

                if not skip_classification:
                    history.append({"role": "user", "content": user_text})
                print(f"  User: {user_text}")

                if not skip_classification:
                    # --- Intent classification ---
                    # Speculative op_spec for follow-up latency optimization
                    # Report in cache OR one currently running = follow_up_on_previous is valid
                    has_reports = bool(session_cache.all_reports()) or (
                        active_report_task is not None and not active_report_task.done()
                    )
                    if has_reports:
                        speculative_op_task = asyncio.create_task(
                            generate_op_spec(user_text, session_cache.summary(), session_cache.get_latest())
                        )

                    intent_result = await classify_intent(user_text, history, has_reports)
                    intent = intent_result["intent"]
                    confidence = intent_result["confidence"]
                    data_query = intent_result["data_query"]
                    last_intent_result = intent_result  # D-05: store for op_chain after delivery

                # Debug: show classified intent in chat (TEXT_MODE)
                if TEXT_MODE:
                    await websocket.send(json.dumps({
                        "type": "sentence",
                        "text": f"(intent: {intent}, confidence: {confidence:.2f})"
                    }))

                if intent == "new_data_request" and confidence >= 0.6:
                    if speculative_op_task is not None:
                        speculative_op_task.cancel()
                    # Fire report immediately — no confirmation gate
                    query = data_query or user_text

                    # FOLLOW-04: Check cache for overlapping data before firing pipeline
                    overlaps = session_cache.find_overlapping(query)
                    if overlaps:
                        overlap_hint = overlaps[0]["query"]
                        hint_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                f"[INTERNAL: You already pulled data earlier that might be relevant — "
                                f'the query was: "{overlap_hint}". '
                                "Ask if they want you to work with that existing data instead of pulling new. "
                                "One sentence, natural. Stay in character.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        hint_reply = await handle_llm_response(websocket, hint_messages, tts_client, _ce)
                        if hint_reply:
                            history.append({"role": "assistant", "content": hint_reply})
                        pending_overlap_query = query
                        continue  # Do NOT fire call_report_api yet — wait for user response

                    active_report_query = query
                    active_report_task = asyncio.create_task(call_report_api(query))
                    # LLM-generated ack in Miyako's voice
                    ack_messages = list(history) + [{
                        "role": "user",
                        "content": (
                            "[INTERNAL: You just kicked off a data pull for the user. "
                            "Give a short, natural one-sentence acknowledgment that you're on it. "
                            "Vary your phrasing — don't repeat yourself across turns.]"
                        ),
                    }]
                    cancel_event = asyncio.Event()
                    ack_reply = await handle_llm_response(websocket, ack_messages, tts_client, cancel_event)
                    if ack_reply:
                        history.append({"role": "assistant", "content": ack_reply})
                    continue

                elif intent == "new_data_request" and confidence < 0.6:
                    if speculative_op_task is not None:
                        speculative_op_task.cancel()
                    # Ambiguous — ask a clarifying question (per INTENT-06)
                    clarify_messages = list(history) + [{
                        "role": "user",
                        "content": (
                            "[INTERNAL: The user might be asking for data but it's unclear. "
                            "Ask a brief, natural clarifying question to understand what they want. "
                            "Don't mention 'reports' or 'data requests' — just ask naturally.]"
                        ),
                    }]
                    cancel_event = asyncio.Event()
                    clarify_reply = await handle_llm_response(websocket, clarify_messages, tts_client, cancel_event)
                    if clarify_reply:
                        history.append({"role": "assistant", "content": clarify_reply})
                    continue

                elif intent == "follow_up_on_previous" and session_cache.all_reports():
                    # FOLLOW-02: LLM interprets follow-up via guided_json op spec
                    if speculative_op_task is not None:
                        op_spec_result = await speculative_op_task
                    else:
                        op_spec_result = await generate_op_spec(
                            user_text, session_cache.summary(), session_cache.get_latest()
                        )

                    # LLM parse error — voice a natural hint before re-firing
                    if op_spec_result.get("op_type") == "_error":
                        fallback_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                "[INTERNAL: The follow-up operation couldn't parse properly. "
                                "Let the user know naturally that you'll pull fresh data for that. "
                                "One casual sentence — like 'let me grab that fresh for you'. Stay in character.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        hint_reply = await handle_llm_response(websocket, fallback_messages, tts_client, _ce)
                        if hint_reply:
                            history.append({"role": "assistant", "content": hint_reply})
                        query = data_query or user_text
                        active_report_query = query
                        active_report_task = asyncio.create_task(call_report_api(query))
                        continue

                    # Resolve target report
                    target_report = (
                        session_cache.get(op_spec_result.get("report_id"))
                        or session_cache.get_latest()
                    )

                    if target_report is None:
                        # Cache expired — reconstruct query from history context
                        prev_data_query = None
                        for m in reversed(history):
                            if m.get("role") == "user" and m.get("content") and not m["content"].startswith("[INTERNAL"):
                                prev_data_query = m["content"]
                                break
                        if prev_data_query and prev_data_query != user_text:
                            query = f"Based on '{prev_data_query}': {user_text}"
                        else:
                            query = data_query or user_text
                        active_report_query = query
                        active_report_task = asyncio.create_task(call_report_api(query))
                        continue

                    # FOLLOW-05 + D-02: Validate referenced columns with fuzzy matching
                    referenced_col = op_spec_result.get("column")
                    referenced_cols = op_spec_result.get("columns") or []
                    all_referenced = ([referenced_col] if referenced_col else []) + referenced_cols

                    # Resolve columns via fuzzy matching before declaring them missing
                    available_cols = list(target_report["columns"].keys())
                    resolved_cols = {}
                    missing_cols = []
                    for c in all_referenced:
                        if not c:
                            continue
                        if c in target_report["columns"]:
                            resolved_cols[c] = c
                        else:
                            matched = _fuzzy_match_column(c, available_cols)
                            if matched:
                                resolved_cols[c] = matched
                            else:
                                missing_cols.append(c)

                    # Update op_spec with resolved column names
                    if resolved_cols:
                        if op_spec_result.get("column") in resolved_cols:
                            op_spec_result["column"] = resolved_cols[op_spec_result["column"]]
                        if op_spec_result.get("columns"):
                            op_spec_result["columns"] = [resolved_cols.get(c, c) for c in op_spec_result["columns"]]

                    if missing_cols:
                        # Missing column — fire a new data request using the previous query
                        # context + what the user just asked, so the report API has enough
                        # information to fetch the right data (e.g. "what r their names?" alone
                        # is meaningless without knowing they were asking about active customers).
                        prev_query = target_report.get("query", "")
                        if prev_query:
                            query = f"Based on '{prev_query}': {user_text}"
                        else:
                            query = data_query or user_text
                        active_report_query = query
                        active_report_task = asyncio.create_task(call_report_api(query))
                        continue

                    # Execute op spec against cached data
                    executor = CacheExecutor()
                    try:
                        if op_spec_result["op_type"] == "cross_report_compare":
                            secondary_id = op_spec_result.get("compare_report_id")
                            secondary = session_cache.get(secondary_id) if secondary_id else None
                            if secondary is None:
                                raise ValueError("Compare report not found in cache")
                            result = executor.execute_cross_report(op_spec_result, target_report, secondary)
                        else:
                            result = executor.execute(op_spec_result, target_report)
                    except Exception as exec_err:
                        print(f"  Executor error: {exec_err}")
                        error_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                "[INTERNAL: The data operation failed. Let the user know naturally "
                                "and offer to try a different approach or pull fresh data. One sentence.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        err_reply = await handle_llm_response(websocket, error_messages, tts_client, _ce)
                        if err_reply:
                            history.append({"role": "assistant", "content": err_reply})
                        continue

                    # FOLLOW-06: Send report_log frame (same shape as deliver_report_result)
                    await websocket.send(json.dumps({
                        "type": "report_log",
                        "query": user_text,
                        "sql": target_report["sql"],
                        "row_count": result["row_count"],
                        "results": result["rows"],
                        "summary": op_spec_result.get("explanation", ""),
                        "claude_interactions": [],
                        "dashboard_b64": "",
                    }))

                    # Cache the result as a new report (enables chained follow-ups)
                    new_rid = session_cache.store(
                        {"results": result["rows"]},
                        query=user_text,
                        sql=target_report["sql"],
                    )
                    print(f"  Follow-up cached as {new_rid} ({result['row_count']} rows)")

                    # D-03: Push to undo stack
                    if len(undo_stack) >= 5:
                        undo_stack.pop(0)
                    undo_stack.append({
                        "report_id": new_rid,
                        "op_spec": op_spec_result,
                        "pre_op_report_id": target_report["report_id"],
                        "query_text": user_text,
                    })

                    # Voice the results via Gemma + TTS
                    if result["row_count"] == 0:
                        # Zero results — fire a new data request with context rather than
                        # letting Gemma guess or reason from memory.
                        prev_query = target_report.get("query", "")
                        if prev_query:
                            query = f"Based on '{prev_query}': {user_text}"
                        else:
                            query = data_query or user_text
                        active_report_query = query
                        active_report_task = asyncio.create_task(call_report_api(query))
                        continue
                    else:
                        # Always embed the actual rows so Gemma speaks only from real data.
                        all_rows_text = json.dumps(result["rows"], default=str)[:800]
                        voice_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                f"[INTERNAL: Follow-up complete. "
                                f"Operation: {op_spec_result.get('explanation', '')}. "
                                f"Exact results ({result['row_count']} rows):\n{all_rows_text}\n\n"
                                "IMPORTANT: Speak ONLY from the data above. Do not use memory or "
                                "guess. If the data does not answer the question, say so. "
                                "Present naturally, 2-3 sentences max.]"
                            ),
                        }]

                    _ce = asyncio.Event()
                    spoken = await handle_llm_response_text_only(websocket, voice_messages, _ce)
                    if not spoken:
                        spoken = op_spec_result.get("explanation", "Done.")
                    history.append({"role": "assistant", "content": spoken})
                    await websocket.send(json.dumps({"type": "sentence", "text": spoken}))
                    _ce2 = asyncio.Event()
                    await tts_full_response(websocket, spoken, tts_client, _ce2)
                    await websocket.send(json.dumps({"type": "done"}))
                    continue

                elif intent == "follow_up_on_previous" and not session_cache.all_reports():
                    if speculative_op_task is not None:
                        speculative_op_task.cancel()
                    # No cached data — infer a new data request from conversation context.
                    # Find the most recent user data request in history to use as base query.
                    prev_data_query = None
                    for m in reversed(history):
                        if m.get("role") == "user" and m.get("content") and not m["content"].startswith("[INTERNAL"):
                            prev_data_query = m["content"]
                            break
                    if prev_data_query and prev_data_query != user_text:
                        query = f"Based on '{prev_data_query}': {user_text}"
                    else:
                        query = data_query or user_text
                    active_report_query = query
                    active_report_task = asyncio.create_task(call_report_api(query))
                    continue

                elif intent == "list_cached_data":
                    if speculative_op_task is not None:
                        speculative_op_task.cancel()
                    reports = session_cache.all_reports()
                    if not reports:
                        empty_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                "[INTERNAL: The user asked what data is available but nothing has been "
                                "pulled yet this session. Let them know naturally. One sentence.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        empty_reply = await handle_llm_response(websocket, empty_messages, tts_client, _ce)
                        if empty_reply:
                            history.append({"role": "assistant", "content": empty_reply})
                        continue

                    # Build summary from session_cache.summary()
                    cache_summary = session_cache.summary()
                    summary_lines = []
                    for entry in cache_summary:
                        summary_lines.append(f"- \"{entry.get('query', 'unknown')}\" ({entry.get('row_count', 0)} rows)")
                    summary_text = "\n".join(summary_lines)

                    list_messages = list(history) + [{
                        "role": "user",
                        "content": (
                            f"[INTERNAL: The user asked what data is available. Here's what's cached:\n"
                            f"{summary_text}\n\n"
                            "Read this off naturally — like listing what you've already looked up. "
                            "Mention each query and how many rows. Keep it brief and casual.]"
                        ),
                    }]
                    _ce = asyncio.Event()
                    list_reply = await handle_llm_response(websocket, list_messages, tts_client, _ce)
                    if list_reply:
                        history.append({"role": "assistant", "content": list_reply})
                    continue

                elif intent == "undo":
                    if speculative_op_task is not None:
                        speculative_op_task.cancel()
                    if not undo_stack:
                        # Nothing to undo
                        no_undo_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                "[INTERNAL: The user said 'undo' but there's nothing to reverse. "
                                "Let them know naturally. One sentence.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        reply = await handle_llm_response(websocket, no_undo_messages, tts_client, _ce)
                        if reply:
                            history.append({"role": "assistant", "content": reply})
                        continue

                    entry = undo_stack.pop()
                    pre_report = session_cache.get(entry["pre_op_report_id"])
                    if pre_report is None:
                        # TTL expired
                        expired_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                "[INTERNAL: The user wants to undo but the original data has expired. "
                                "Let them know naturally and offer to pull fresh. One sentence.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        reply = await handle_llm_response(websocket, expired_messages, tts_client, _ce)
                        if reply:
                            history.append({"role": "assistant", "content": reply})
                        continue

                    # Send report_log frame with restored data
                    await websocket.send(json.dumps({
                        "type": "report_log",
                        "query": pre_report["query"],
                        "sql": pre_report["sql"],
                        "row_count": pre_report["row_count"],
                        "results": pre_report["rows"],
                        "summary": "",
                        "claude_interactions": [],
                        "dashboard_b64": "",
                    }))
                    # Voice confirmation
                    undo_messages = list(history) + [{
                        "role": "user",
                        "content": (
                            f'[INTERNAL: You just undid the last operation. Back to the data from: '
                            f'"{pre_report["query"]}". Let the user know naturally. One sentence.]'
                        ),
                    }]
                    _ce = asyncio.Event()
                    spoken = await handle_llm_response_text_only(websocket, undo_messages, _ce)
                    if not spoken:
                        spoken = f"Done, back to {pre_report['query']}."
                    history.append({"role": "assistant", "content": spoken})
                    await websocket.send(json.dumps({"type": "sentence", "text": spoken}))
                    _ce2 = asyncio.Event()
                    await tts_full_response(websocket, spoken, tts_client, _ce2)
                    await websocket.send(json.dumps({"type": "done"}))
                    continue

                elif intent == "what_can_i_ask":
                    if speculative_op_task is not None:
                        speculative_op_task.cancel()
                    # Try report API /topics endpoint
                    topics_text = None
                    try:
                        async with httpx.AsyncClient() as _hc:
                            resp = await _hc.get(
                                f"{REPORT_API_URL}/topics",
                                headers={"X-API-Key": REPORT_API_KEY} if REPORT_API_KEY else {},
                                timeout=5.0,
                            )
                            if resp.status_code == 200:
                                topics_data = resp.json()
                                if isinstance(topics_data, list):
                                    topics_text = ", ".join(str(t) for t in topics_data[:20])
                                elif isinstance(topics_data, dict) and topics_data.get("topics"):
                                    topics_text = ", ".join(str(t) for t in topics_data["topics"][:20])
                    except Exception:
                        pass

                    if not topics_text:
                        # Fallback: hardcoded known domains + session cache
                        known_domains = "clients, invoices, tax cases, payments, warehouses, orders, products"
                        cached = session_cache.all_reports()
                        if cached:
                            cached_queries = [r["query"] for r in cached]
                            topics_text = f"{known_domains}. You've already pulled: {', '.join(cached_queries)}"
                        else:
                            topics_text = known_domains

                    discovery_messages = list(history) + [{
                        "role": "user",
                        "content": (
                            f"[INTERNAL: The user wants to know what data topics are available. "
                            f"Available topics: {topics_text}. "
                            "List these naturally — like telling a colleague what's in the system. "
                            "Keep it brief and conversational. Don't read a technical list.]"
                        ),
                    }]
                    _ce = asyncio.Event()
                    reply = await handle_llm_response(websocket, discovery_messages, tts_client, _ce)
                    if reply:
                        history.append({"role": "assistant", "content": reply})
                    continue

                elif intent == "compare_reports":
                    if speculative_op_task is not None:
                        speculative_op_task.cancel()
                    query = data_query or user_text
                    # Split on "and", "with", "versus", "vs"
                    parts = re.split(r'\b(?:and|with|versus|vs\.?)\b', query, maxsplit=1, flags=re.IGNORECASE)

                    if len(parts) < 2:
                        # Can't extract two topics -- ask for clarification
                        clarify_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                "[INTERNAL: The user wants to compare two things but you couldn't "
                                "figure out the two topics. Ask them to specify the two things to compare. "
                                "One sentence, natural.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        reply = await handle_llm_response(websocket, clarify_messages, tts_client, _ce)
                        if reply:
                            history.append({"role": "assistant", "content": reply})
                        continue

                    topic_a = parts[0].strip().lstrip("compare ").strip()
                    topic_b = parts[1].strip()

                    # Check for >80% word overlap (per RESEARCH.md Pitfall 6)
                    words_a = set(topic_a.lower().split())
                    words_b = set(topic_b.lower().split())
                    if words_a and words_b:
                        overlap = len(words_a & words_b) / max(len(words_a), len(words_b))
                        if overlap > 0.8:
                            # Topics are too similar -- treat as single new_data_request
                            active_report_query = query
                            active_report_task = asyncio.create_task(call_report_api(query))
                            ack_messages = list(history) + [{
                                "role": "user",
                                "content": (
                                    "[INTERNAL: Pulling that data now. Brief ack. One sentence.]"
                                ),
                            }]
                            _ce = asyncio.Event()
                            ack_reply = await handle_llm_response(websocket, ack_messages, tts_client, _ce)
                            if ack_reply:
                                history.append({"role": "assistant", "content": ack_reply})
                            continue

                    # Voice progress
                    progress_messages = list(history) + [{
                        "role": "user",
                        "content": (
                            "[INTERNAL: You're about to pull two sets of data to compare them. "
                            "Give a short natural ack like 'pulling both now'. One sentence.]"
                        ),
                    }]
                    _ce = asyncio.Event()
                    ack_reply = await handle_llm_response(websocket, progress_messages, tts_client, _ce)
                    if ack_reply:
                        history.append({"role": "assistant", "content": ack_reply})

                    # Fire both concurrently (per D-06)
                    task_a = asyncio.create_task(call_report_api(topic_a))
                    task_b = asyncio.create_task(call_report_api(topic_b))
                    try:
                        res_a, res_b = await asyncio.gather(task_a, task_b)
                    except Exception as e:
                        print(f"  Compare fetch error: {e}")
                        error_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                "[INTERNAL: One or both data pulls failed. Let the user know "
                                "naturally. One sentence.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        err_reply = await handle_llm_response(websocket, error_messages, tts_client, _ce)
                        if err_reply:
                            history.append({"role": "assistant", "content": err_reply})
                        continue

                    # Cache both
                    rid_a = session_cache.store(res_a, query=topic_a, sql=res_a.get("sql") or "")
                    rid_b = session_cache.store(res_b, query=topic_b, sql=res_b.get("sql") or "")
                    report_a = session_cache.get(rid_a)
                    report_b = session_cache.get(rid_b)

                    if not report_a or not report_b or not report_a["rows"] or not report_b["rows"]:
                        error_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                "[INTERNAL: One of the data pulls returned empty. Let the user know. One sentence.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        err_reply = await handle_llm_response(websocket, error_messages, tts_client, _ce)
                        if err_reply:
                            history.append({"role": "assistant", "content": err_reply})
                        continue

                    # Find shared column
                    cols_a = set(report_a["columns"].keys())
                    cols_b = set(report_b["columns"].keys())
                    shared_cols = cols_a & cols_b
                    if not shared_cols:
                        no_shared_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                f"[INTERNAL: You pulled {topic_a} and {topic_b} but they don't share "
                                "any column names for comparison. Let the user know naturally. One sentence.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        reply = await handle_llm_response(websocket, no_shared_messages, tts_client, _ce)
                        if reply:
                            history.append({"role": "assistant", "content": reply})
                        continue

                    compare_col = sorted(shared_cols)[0]
                    executor = CacheExecutor()
                    try:
                        result = executor.execute_cross_report(
                            {"op_type": "cross_report_compare", "compare_column": compare_col, "explanation": f"compare on {compare_col}"},
                            report_a, report_b,
                        )
                    except Exception as e:
                        print(f"  Cross-report error: {e}")
                        error_messages = list(history) + [{
                            "role": "user",
                            "content": "[INTERNAL: The comparison failed. Let the user know. One sentence.]",
                        }]
                        _ce = asyncio.Event()
                        reply = await handle_llm_response(websocket, error_messages, tts_client, _ce)
                        if reply:
                            history.append({"role": "assistant", "content": reply})
                        continue

                    # Send report_log frame
                    await websocket.send(json.dumps({
                        "type": "report_log",
                        "query": user_text,
                        "sql": "",
                        "row_count": result["row_count"],
                        "results": result["rows"],
                        "summary": "",
                        "claude_interactions": [],
                        "dashboard_b64": "",
                    }))

                    # Cache comparison result
                    session_cache.store({"results": result["rows"]}, query=user_text, sql="")

                    # Voice results
                    preview_rows = result["rows"][:5]
                    preview_text = json.dumps(preview_rows, default=str)[:500]
                    voice_messages = list(history) + [{
                        "role": "user",
                        "content": (
                            f"[INTERNAL: Comparison done. Merged {topic_a} and {topic_b} on '{compare_col}'. "
                            f"Result: {result['row_count']} rows. Preview: {preview_text}\n\n"
                            "Present the comparison naturally. 2-3 sentences.]"
                        ),
                    }]
                    _ce = asyncio.Event()
                    spoken = await handle_llm_response_text_only(websocket, voice_messages, _ce)
                    if not spoken:
                        spoken = f"Compared {topic_a} and {topic_b} on {compare_col} -- {result['row_count']} matching rows."
                    history.append({"role": "assistant", "content": spoken})
                    await websocket.send(json.dumps({"type": "sentence", "text": spoken}))
                    _ce2 = asyncio.Event()
                    await tts_full_response(websocket, spoken, tts_client, _ce2)
                    await websocket.send(json.dumps({"type": "done"}))
                    continue

                elif intent == "confirm" and pending_suggestion_spec is not None:
                    if speculative_op_task is not None:
                        speculative_op_task.cancel()
                    # Execute the suggested broadened spec
                    target = session_cache.get_latest()
                    if target:
                        executor = CacheExecutor()
                        try:
                            result = executor.execute(pending_suggestion_spec, target)
                            pending_suggestion_spec = None  # Clear after execution

                            await websocket.send(json.dumps({
                                "type": "report_log",
                                "query": user_text,
                                "sql": target["sql"],
                                "row_count": result["row_count"],
                                "results": result["rows"],
                                "summary": "",
                                "claude_interactions": [],
                                "dashboard_b64": "",
                            }))

                            if result["row_count"] > 0:
                                new_rid = session_cache.store(
                                    {"results": result["rows"]}, query=user_text, sql=target["sql"]
                                )
                                preview = json.dumps(result["rows"][:5], default=str)[:500]
                                voice_messages = list(history) + [{
                                    "role": "user",
                                    "content": (
                                        f"[INTERNAL: The broader search worked. "
                                        f"{result['row_count']} rows. Preview: {preview}\n\n"
                                        "Present naturally. 2-3 sentences.]"
                                    ),
                                }]
                            else:
                                voice_messages = list(history) + [{
                                    "role": "user",
                                    "content": (
                                        "[INTERNAL: Even the broader search found nothing. "
                                        "Let the user know definitively. One sentence.]"
                                    ),
                                }]

                            _ce = asyncio.Event()
                            spoken = await handle_llm_response_text_only(websocket, voice_messages, _ce)
                            if not spoken:
                                spoken = "Here's what I found with the broader search."
                            history.append({"role": "assistant", "content": spoken})
                            await websocket.send(json.dumps({"type": "sentence", "text": spoken}))
                            _ce2 = asyncio.Event()
                            await tts_full_response(websocket, spoken, tts_client, _ce2)
                            await websocket.send(json.dumps({"type": "done"}))
                        except Exception as e:
                            print(f"  Suggestion execution error: {e}")
                            pending_suggestion_spec = None
                    else:
                        pending_suggestion_spec = None
                    continue

                elif intent == "cancel" and pending_suggestion_spec is not None:
                    if speculative_op_task is not None:
                        speculative_op_task.cancel()
                    pending_suggestion_spec = None
                    cancel_messages = list(history) + [{
                        "role": "user",
                        "content": "[INTERNAL: User cancelled the suggestion. Acknowledge briefly. One sentence.]",
                    }]
                    _ce = asyncio.Event()
                    reply = await handle_llm_response(websocket, cancel_messages, tts_client, _ce)
                    if reply:
                        history.append({"role": "assistant", "content": reply})
                    continue

                # confirm and cancel intents fall through to normal_chat
                # normal_chat falls through to the existing generation phase below
                if speculative_op_task is not None:
                    speculative_op_task.cancel()

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
                    await deliver_report_result(websocket, active_report_task, history, tts_client, active_report_query, session_cache=session_cache)
                    if last_intent_result:
                        await _apply_op_chain(websocket, last_intent_result, session_cache, active_report_query)
                        last_intent_result = None
                    active_report_task = None
                    active_report_query = ""
    finally:
        active_ws = None
        print(f"Client disconnected: {websocket.remote_address}")


async def main():
    print(f"Sei Engine listening on {BIND_ADDR}:{PORT}")
    print(f"LLM: {LLM_URL} (model: {MODEL_NAME}, auth: {'Bearer ***' if LLM_API_KEY else 'none'})")
    print(f"TTS: {TTS_URL} (reference: {TTS_REFERENCE_ID})")
    print(f"Auth: {'<from env>' if os.environ.get('SEI_AUTH_TOKEN') else '<dev mode>'}")
    async with serve(handler, BIND_ADDR, PORT, process_request=process_request) as server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSei Engine stopped.")
