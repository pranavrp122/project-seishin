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
WAV_HEADER_SIZE = 44
EMOTION_RE = re.compile(r'^\((\w[\w\s]*)\)\s*')

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
    active_ws = connection


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


def parse_emotion(text: str) -> str:
    """Convert (emotion) prefix to [emotion] tag for Fish Speech."""
    m = EMOTION_RE.match(text)
    if m:
        emotion = m.group(1).strip()
        clean = text[m.end():]
        return f"[{emotion}] {clean}"
    return text


def drain_queue(q: asyncio.Queue) -> None:
    """Remove all pending items from queue without blocking."""
    while not q.empty():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            break


async def tts_sentence(ws, text: str, tts_client: httpx.AsyncClient, cancel_event: asyncio.Event):
    """Send sentence to Fish Speech TTS and stream PCM audio to WebSocket client."""
    tts_text = parse_emotion(text)
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
                await ws.send(json.dumps({"type": "error", "message": f"TTS error: {response.status_code}"}))
                return

            header_buf = bytearray()
            header_stripped = False
            async for chunk in response.aiter_bytes():
                if cancel_event.is_set():
                    return
                if not header_stripped:
                    header_buf.extend(chunk)
                    if len(header_buf) < WAV_HEADER_SIZE:
                        continue
                    if header_buf[:4] != b'RIFF':
                        print(f"  Warning: TTS response missing WAV header, streaming raw")
                        await ws.send(bytes(header_buf))
                    else:
                        remainder = bytes(header_buf[WAV_HEADER_SIZE:])
                        if remainder:
                            await ws.send(remainder)
                    header_stripped = True
                    continue
                await ws.send(chunk)  # Binary WebSocket frame
    except httpx.ConnectError:
        print(f"  TTS connection failed: {TTS_URL}")
        await ws.send(json.dumps({"type": "error", "message": "TTS service unavailable"}))
    except Exception as e:
        print(f"  TTS error: {e}")
        await ws.send(json.dumps({"type": "error", "message": f"TTS error: {e}"}))


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
    """Stream LLM tokens, buffer sentences, dispatch to TTS, stream audio."""
    sentence_buffer = ""
    reply_parts = []
    t0 = time.perf_counter()
    first_token = True

    sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def tts_consumer():
        """Process sentences from queue and stream TTS audio to client."""
        while True:
            if cancel_event.is_set():
                break
            try:
                sentence = await asyncio.wait_for(sentence_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            if sentence is None:
                break
            if cancel_event.is_set():
                break
            await ws.send(json.dumps({"type": "sentence", "text": sentence}))
            await tts_sentence(ws, sentence, tts_client, cancel_event)

    tts_task = asyncio.create_task(tts_consumer())

    async for token in stream_llm(messages, cancel_event):
        if tts_task.done():
            break
        if first_token:
            ttft = (time.perf_counter() - t0) * 1000
            print(f"  TTFT: {ttft:.0f}ms", flush=True)
            first_token = False

        reply_parts.append(token)
        if cancel_event.is_set():
            break
        sentence_buffer += token

        if SENTENCE_END.search(sentence_buffer):
            await sentence_queue.put(sentence_buffer.strip())
            sentence_buffer = ""

    if cancel_event.is_set():
        drain_queue(sentence_queue)
    else:
        if sentence_buffer.strip():
            await sentence_queue.put(sentence_buffer.strip())
        await sentence_queue.put(None)  # Poison pill

    # Always signal TTS consumer to stop if cancelled
    if cancel_event.is_set():
        await sentence_queue.put(None)  # Ensure consumer exits

    await tts_task

    if cancel_event.is_set():
        await ws.send(json.dumps({"type": "interrupted"}))
    else:
        await ws.send(json.dumps({"type": "done"}))
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"  Total: {elapsed:.0f}ms", flush=True)

    return "".join(reply_parts).strip()


async def handler(websocket):
    """Handle a single WebSocket client session."""
    global active_ws
    history = build_initial_messages()
    print(f"Client connected: {websocket.remote_address}")

    try:
        async with httpx.AsyncClient() as tts_client:
            async for raw in websocket:
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

                try:
                    reply = await handle_llm_response(websocket, history, tts_client)
                except Exception as e:
                    print(f"  LLM error: {e}")
                    await websocket.send(json.dumps({"type": "error", "message": str(e)}))
                    history.pop()
                    continue

                if is_quality_response(reply):
                    history.append({"role": "assistant", "content": reply})
                else:
                    history.pop()
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
