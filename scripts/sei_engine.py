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
import re
import time
from http import HTTPStatus
from collections.abc import AsyncGenerator

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
import httpx
import ormsgpack

from system_prompts import SYSTEM_PROMPT, SEED_HISTORY, DODGE_PHRASES

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
REPETITION_PENALTY = float(os.environ.get("SEI_REPETITION_PENALTY", "1.15"))

TTS_URL = os.environ.get("SEI_TTS_URL", "http://127.0.0.1:8080")
TTS_REFERENCE_ID = os.environ.get("TTS_REFERENCE_ID", "archie")
TTS_CHUNK_LENGTH = int(os.environ.get("TTS_CHUNK_LENGTH", "200"))
TTS_TOP_P = float(os.environ.get("TTS_TOP_P", "0.8"))
TTS_TEMPERATURE = float(os.environ.get("TTS_TEMPERATURE", "0.8"))
TTS_REPETITION_PENALTY_TTS = float(os.environ.get("TTS_REPETITION_PENALTY", "1.1"))
TTS_MAX_NEW_TOKENS = int(os.environ.get("TTS_MAX_NEW_TOKENS", "1024"))
WAV_HEADER_SIZE = 44  # Fallback if data chunk parsing fails
EMOTION_RE = re.compile(r'^\((\w[\w\s]*)\)\s*')


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

SENTENCE_END = re.compile(r'[.!?]["\')\]]?(?:\s|$)')

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
    return bool(reply) and len(reply) >= 10 and not any(
        p in reply.lower() for p in DODGE_PHRASES
    )


def extract_emotion(text: str) -> tuple[str, str]:
    """Extract (emotion) prefix, return (emotion_tag, clean_text).

    Returns e.g. ("[happy]", "That sounds great!") or ("", "No emotion here.").
    """
    m = EMOTION_RE.match(text)
    if m:
        emotion = m.group(1).strip()
        clean = text[m.end():]
        return f"[{emotion}]", clean
    return "", text


def apply_emotion(text: str, emotion_tag: str) -> str:
    """Prepend emotion tag to text for Fish Speech if tag is set."""
    if emotion_tag:
        return f"{emotion_tag} {text}"
    return text


async def tts_full_response(ws, text: str, tts_client: httpx.AsyncClient, cancel_event: asyncio.Event):
    """Send full LLM response to Fish Speech TTS and stream PCM audio back.

    Emotion tag at the start of the response naturally covers the entire output.
    Fish Speech streams audio chunks back via streaming=True.
    """
    # Convert (emotion) prefix to [emotion] tag for Fish Speech
    emotion_tag, clean = extract_emotion(text)
    tts_text = apply_emotion(clean, emotion_tag) if emotion_tag else text
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
            async for chunk in response.aiter_bytes():
                if cancel_event.is_set():
                    return
                if data_offset is None:
                    header_buf.extend(chunk)
                    data_offset = find_wav_data_offset(header_buf)
                    if data_offset is None:
                        if len(header_buf) > 1024:
                            # Safety bail: assume standard 44-byte header
                            data_offset = WAV_HEADER_SIZE
                            remainder = bytes(header_buf[data_offset:])
                            if remainder:
                                await ws.send(remainder)
                        continue
                    remainder = bytes(header_buf[data_offset:])
                    if remainder:
                        await ws.send(remainder)
                    continue
                await ws.send(chunk)  # Binary WebSocket frame
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
    """Stream LLM tokens, collect full response, then TTS the whole thing.

    Text display: sentence frames sent to client as LLM generates (progressive UI).
    Audio: full response sent to Fish Speech as one request after LLM completes,
    so the emotion tag at the start naturally covers the entire response.
    Fish Speech streams audio chunks back (streaming=True).
    """
    sentence_buffer = ""
    reply_parts = []
    sentences = []  # Collected for text display
    t0 = time.perf_counter()
    first_token = True

    # Phase 1: Stream LLM, send sentence frames for text display, accumulate full reply
    async for token in stream_llm(messages, cancel_event):
        if first_token:
            ttft = (time.perf_counter() - t0) * 1000
            print(f"  TTFT: {ttft:.0f}ms", flush=True)
            first_token = False

        reply_parts.append(token)
        if cancel_event.is_set():
            break
        sentence_buffer += token

        m = SENTENCE_END.search(sentence_buffer)
        if m:
            end_pos = m.end()
            sentence = sentence_buffer[:end_pos].strip()
            sentence_buffer = sentence_buffer[end_pos:]
            if sentence:
                sentences.append(sentence)
                await ws.send(json.dumps({"type": "sentence", "text": sentence}))

    # Flush trailing text
    if not cancel_event.is_set() and sentence_buffer.strip():
        sentences.append(sentence_buffer.strip())
        await ws.send(json.dumps({"type": "sentence", "text": sentence_buffer.strip()}))

    full_reply = "".join(reply_parts).strip()

    if cancel_event.is_set():
        await ws.send(json.dumps({"type": "interrupted"}))
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"  Interrupted at {elapsed:.0f}ms", flush=True)
        return full_reply

    # Phase 2: Send full response to Fish Speech, stream audio back
    if full_reply:
        llm_done = (time.perf_counter() - t0) * 1000
        print(f"  LLM done: {llm_done:.0f}ms, sending full text to TTS ({len(full_reply)} chars)", flush=True)
        await tts_full_response(ws, full_reply, tts_client, cancel_event)

    if cancel_event.is_set():
        await ws.send(json.dumps({"type": "interrupted"}))
    else:
        await ws.send(json.dumps({"type": "done"}))
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"  Total: {elapsed:.0f}ms", flush=True)

    return full_reply


async def handler(websocket):
    """Handle a single WebSocket client session with barge-in support."""
    global active_ws
    active_ws = websocket  # Set here where finally block guarantees cleanup
    history = build_initial_messages()
    print(f"Client connected: {websocket.remote_address}")

    try:
        async with httpx.AsyncClient() as tts_client:
            pending_msg = None  # Buffered message from stop-listener

            while True:
                # --- Phase A: Wait for user message ---
                if pending_msg:
                    msg = pending_msg
                    pending_msg = None
                else:
                    try:
                        raw = await websocket.recv()
                    except ConnectionClosed:
                        break
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                        continue

                if msg.get("type") != "message" or not msg.get("text"):
                    await websocket.send(json.dumps({"type": "error", "message": "Expected {type: message, text: ...}"}))
                    continue

                user_text = msg["text"].strip()
                if not user_text:
                    continue

                history.append({"role": "user", "content": user_text})
                print(f"  User: {user_text}")

                # --- Phase B: Concurrent generation + stop listener ---
                cancel_event = asyncio.Event()

                gen_task = asyncio.create_task(
                    handle_llm_response(websocket, history, tts_client, cancel_event)
                )

                stop_result = {"new_msg": None}

                async def listen_for_stop():
                    """Listen for stop or new message during generation. Owns recv()."""
                    while True:
                        try:
                            raw = await websocket.recv()
                        except ConnectionClosed:
                            cancel_event.set()
                            return
                        try:
                            parsed = json.loads(raw)
                        except json.JSONDecodeError:
                            continue  # Ignore malformed messages during generation
                        if parsed.get("type") == "stop":
                            cancel_event.set()
                            return
                        elif parsed.get("type") == "message" and parsed.get("text"):
                            # New message = implicit interrupt
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
