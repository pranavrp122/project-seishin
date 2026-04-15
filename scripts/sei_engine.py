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

from system_prompts import SYSTEM_PROMPT, SEED_HISTORY, DODGE_PHRASES

# --- Configuration ---
AUTH_TOKEN = os.environ.get("SEI_AUTH_TOKEN", "test-token-change-me")
BIND_ADDR = os.environ.get("SEI_BIND", "127.0.0.1")
PORT = int(os.environ.get("SEI_PORT", "5052"))
LLM_URL = os.environ.get("SEI_LLM_URL", "http://127.0.0.1:8000")
MODEL_NAME = os.environ.get("SEI_MODEL_NAME", "gemma-4")
MAX_TOKENS = int(os.environ.get("SEI_MAX_TOKENS", "300"))
TEMPERATURE = float(os.environ.get("SEI_TEMPERATURE", "0.7"))
REPETITION_PENALTY = float(os.environ.get("SEI_REPETITION_PENALTY", "1.15"))

SENTENCE_END = re.compile(r'[.!?]["\')\]]?\s')

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


async def stream_llm(messages: list[dict]) -> AsyncGenerator[str, None]:
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


async def handle_llm_response(ws, messages: list[dict]) -> str:
    """Stream LLM tokens, buffer into sentences, dispatch as JSON frames."""
    sentence_buffer = ""
    reply_parts = []
    t0 = time.perf_counter()
    first_token = True

    async for token in stream_llm(messages):
        if first_token:
            ttft = (time.perf_counter() - t0) * 1000
            print(f"  TTFT: {ttft:.0f}ms", flush=True)
            first_token = False

        reply_parts.append(token)
        sentence_buffer += token

        if SENTENCE_END.search(sentence_buffer):
            await ws.send(json.dumps({"type": "sentence", "text": sentence_buffer.strip()}))
            sentence_buffer = ""

    # Flush remaining buffer
    if sentence_buffer.strip():
        await ws.send(json.dumps({"type": "sentence", "text": sentence_buffer.strip()}))

    await ws.send(json.dumps({"type": "done"}))

    elapsed = (time.perf_counter() - t0) * 1000
    print(f"  Total: {elapsed:.0f}ms", flush=True)

    return "".join(reply_parts).strip()


async def handler(websocket):
    """Handle a single WebSocket client session."""
    global active_ws
    active_ws = websocket
    history = build_initial_messages()
    print(f"Client connected: {websocket.remote_address}")

    try:
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
                reply = await handle_llm_response(websocket, history)
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
    print(f"Auth: {'<from env>' if os.environ.get('SEI_AUTH_TOKEN') else 'test-token-change-me (DEFAULT)'}")
    async with serve(handler, BIND_ADDR, PORT, process_request=process_request) as server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSei Engine stopped.")
