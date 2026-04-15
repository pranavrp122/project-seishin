#!/usr/bin/env python3
"""Automated tests for Sei Engine.

Offline tests (no vLLM): auth, session gating, protocol validation.
Online tests (vLLM required): LLM streaming, sentence dispatch, conversation memory.
TTS tests (vLLM + Fish Speech required): binary audio frames, PCM format, incremental streaming, latency.

Usage:
    python scripts/test_sei_engine.py            # offline tests only
    python scripts/test_sei_engine.py --online    # + LLM tests (vLLM required)
    python scripts/test_sei_engine.py --tts       # + TTS tests (vLLM + Fish Speech required)
"""
import asyncio
import json
import os
import struct
import sys
import time

import websockets
from websockets.exceptions import InvalidStatus

SERVER_URL = os.environ.get("SEI_TEST_URL", "ws://127.0.0.1:5052")
AUTH_TOKEN = os.environ.get("SEI_AUTH_TOKEN", "test-token-change-me")

passed = 0
total = 0


async def connect(token=None):
    """Helper to open a WebSocket connection with optional auth."""
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return await websockets.connect(SERVER_URL, additional_headers=headers)


def report(test_num, name, ok, detail=""):
    global passed, total
    total += 1
    if ok:
        passed += 1
        print(f"[TEST {test_num}] {name}\n  PASS{': ' + detail if detail else ''}")
    else:
        print(f"[TEST {test_num}] {name}\n  FAIL{': ' + detail if detail else ''}")


async def test_auth_valid_token():
    """Connect with valid Bearer token - should succeed."""
    try:
        ws = await connect(AUTH_TOKEN)
        await ws.close()
        report(1, "Connect with valid token", True)
    except Exception as e:
        report(1, "Connect with valid token", False, str(e))


async def test_auth_invalid_token():
    """Connect with wrong token - expect 401."""
    try:
        ws = await connect("wrong-token")
        await ws.close()
        report(2, "Reject invalid token (expect 401)", False, "Connection was accepted")
    except InvalidStatus as e:
        report(2, "Reject invalid token (expect 401)", e.response.status_code == 401,
               f"Got {e.response.status_code}")
    except Exception as e:
        report(2, "Reject invalid token (expect 401)", False, str(e))


async def test_auth_no_token():
    """Connect with no Authorization header - expect 401."""
    try:
        ws = await connect()
        await ws.close()
        report(3, "Reject missing token (expect 401)", False, "Connection was accepted")
    except InvalidStatus as e:
        report(3, "Reject missing token (expect 401)", e.response.status_code == 401,
               f"Got {e.response.status_code}")
    except Exception as e:
        report(3, "Reject missing token (expect 401)", False, str(e))


async def test_single_session():
    """Second connection while first is active should get 503."""
    ws1 = None
    try:
        ws1 = await connect(AUTH_TOKEN)
        # Attempt second connection
        try:
            ws2 = await connect(AUTH_TOKEN)
            await ws2.close()
            report(4, "Reject second session (expect 503)", False, "Second connection accepted")
        except InvalidStatus as e:
            ok = e.response.status_code == 503
            report(4, "Reject second session (expect 503)", ok, f"Got {e.response.status_code}")
        except Exception as e:
            report(4, "Reject second session (expect 503)", False, str(e))
    except Exception as e:
        report(4, "Reject second session (expect 503)", False, f"First connection failed: {e}")
    finally:
        if ws1:
            await ws1.close()


async def test_invalid_message_format():
    """Send invalid message types - expect error frames."""
    ws = None
    try:
        ws = await connect(AUTH_TOKEN)
        # Send unknown type
        await ws.send(json.dumps({"type": "unknown"}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        got_error_1 = resp.get("type") == "error"

        # Send non-JSON
        await ws.send("not json at all")
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        got_error_2 = resp.get("type") == "error"

        report(5, "Error frames for invalid messages", got_error_1 and got_error_2,
               f"unknown_type_error={got_error_1}, bad_json_error={got_error_2}")
    except Exception as e:
        report(5, "Error frames for invalid messages", False, str(e))
    finally:
        if ws:
            await ws.close()


async def test_session_cleanup_on_disconnect():
    """After disconnect, a new connection should succeed."""
    try:
        ws1 = await connect(AUTH_TOKEN)
        await ws1.close()
        await asyncio.sleep(0.5)
        ws2 = await connect(AUTH_TOKEN)
        await ws2.close()
        report(6, "Session cleanup after disconnect", True)
    except Exception as e:
        report(6, "Session cleanup after disconnect", False, str(e))


async def test_message_protocol():
    """Send message, expect sentence + done frames. (Requires vLLM)"""
    ws = None
    try:
        ws = await connect(AUTH_TOKEN)
        await ws.send(json.dumps({"type": "message", "text": "Say hello in one sentence."}))

        frames = []
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(raw, bytes):
                continue  # skip binary audio frames
            frame = json.loads(raw)
            frames.append(frame)
            if frame.get("type") in ("done", "error"):
                break

        sentence_frames = [f for f in frames if f.get("type") == "sentence"]
        done_frames = [f for f in frames if f.get("type") == "done"]
        has_sentences = len(sentence_frames) >= 1 and all(f.get("text") for f in sentence_frames)
        has_done = len(done_frames) == 1

        report(7, "Message protocol (sentence + done)", has_sentences and has_done,
               f"{len(sentence_frames)} sentence frames, done={has_done}")
    except Exception as e:
        report(7, "Message protocol (sentence + done)", False, str(e))
    finally:
        if ws:
            await ws.close()


async def test_sentence_buffering():
    """Multi-sentence prompt should produce multiple sentence frames. (Requires vLLM)"""
    ws = None
    try:
        ws = await connect(AUTH_TOKEN)
        await ws.send(json.dumps({"type": "message", "text": "Tell me two facts about the ocean."}))

        sentence_count = 0
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(raw, bytes):
                continue
            frame = json.loads(raw)
            if frame.get("type") == "sentence":
                sentence_count += 1
            if frame.get("type") in ("done", "error"):
                break

        report(8, "Sentence buffering (multiple sentences)", sentence_count > 1,
               f"Got {sentence_count} sentence frames")
    except Exception as e:
        report(8, "Sentence buffering (multiple sentences)", False, str(e))
    finally:
        if ws:
            await ws.close()


async def test_conversation_memory():
    """Second turn should reference context from first. (Requires vLLM)"""
    ws = None
    try:
        ws = await connect(AUTH_TOKEN)

        # Turn 1: establish context
        await ws.send(json.dumps({"type": "message", "text": "My favorite color is blue. Remember that."}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(raw, bytes):
                continue
            frame = json.loads(raw)
            if frame.get("type") in ("done", "error"):
                break

        # Turn 2: ask about context
        await ws.send(json.dumps({"type": "message", "text": "What is my favorite color?"}))
        response_text = ""
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(raw, bytes):
                continue
            frame = json.loads(raw)
            if frame.get("type") == "sentence":
                response_text += frame.get("text", "")
            if frame.get("type") in ("done", "error"):
                break

        has_blue = "blue" in response_text.lower()
        report(9, "Conversation memory across turns", has_blue,
               f"Response: {response_text[:100]}")
    except Exception as e:
        report(9, "Conversation memory across turns", False, str(e))
    finally:
        if ws:
            await ws.close()


async def test_tts_binary_frames():
    """Send message, expect sentence text frames AND binary audio frames. (Requires vLLM + Fish Speech)"""
    ws = None
    try:
        ws = await connect(AUTH_TOKEN)
        await ws.send(json.dumps({"type": "message", "text": "Say hello in one sentence."}))

        text_frames = []
        binary_frames = []
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(raw, bytes):
                binary_frames.append(raw)
            else:
                frame = json.loads(raw)
                text_frames.append(frame)
                if frame.get("type") in ("done", "error"):
                    break

        has_sentence = any(f.get("type") == "sentence" for f in text_frames)
        has_done = any(f.get("type") == "done" for f in text_frames)
        has_audio = len(binary_frames) > 0
        # Verify audio is PCM int16 (even number of bytes)
        audio_aligned = all(len(b) % 2 == 0 for b in binary_frames)

        report(10, "TTS binary frames received", has_sentence and has_done and has_audio and audio_aligned,
               f"sentences={sum(1 for f in text_frames if f.get('type')=='sentence')}, "
               f"audio_chunks={len(binary_frames)}, "
               f"total_audio_bytes={sum(len(b) for b in binary_frames)}, "
               f"int16_aligned={audio_aligned}")
    except Exception as e:
        report(10, "TTS binary frames received", False, str(e))
    finally:
        if ws:
            await ws.close()


async def test_tts_audio_format():
    """Verify audio is PCM int16 44.1kHz mono (reasonable sample values). (Requires vLLM + Fish Speech)"""
    ws = None
    try:
        ws = await connect(AUTH_TOKEN)
        await ws.send(json.dumps({"type": "message", "text": "Say the word hello."}))

        audio_bytes = bytearray()
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(raw, bytes):
                audio_bytes.extend(raw)
            else:
                frame = json.loads(raw)
                if frame.get("type") in ("done", "error"):
                    break

        # Verify: got audio, int16-aligned, reasonable sample values
        has_audio = len(audio_bytes) > 0
        is_aligned = len(audio_bytes) % 2 == 0
        # Check samples are in int16 range (not garbled by WAV header)
        if is_aligned and has_audio:
            samples = struct.unpack(f'<{len(audio_bytes)//2}h', audio_bytes)
            max_sample = max(abs(s) for s in samples[:1000])  # Check first 1000 samples
            reasonable_range = max_sample < 32768  # int16 max
            no_wav_header = audio_bytes[:4] != b'RIFF'  # WAV header stripped
        else:
            reasonable_range = False
            no_wav_header = False

        # Estimate duration: bytes / 2 (int16) / 44100 (sample rate)
        duration_sec = len(audio_bytes) / 2 / 44100 if has_audio else 0

        report(11, "Audio format PCM int16 44.1kHz", has_audio and is_aligned and reasonable_range and no_wav_header,
               f"bytes={len(audio_bytes)}, duration={duration_sec:.1f}s, "
               f"max_sample={max_sample if has_audio and is_aligned else 'N/A'}, "
               f"no_wav_header={no_wav_header}")
    except Exception as e:
        report(11, "Audio format PCM int16 44.1kHz", False, str(e))
    finally:
        if ws:
            await ws.close()


async def test_tts_incremental_streaming():
    """Verify audio arrives incrementally (multiple chunks, not one blob). (Requires vLLM + Fish Speech)"""
    ws = None
    try:
        ws = await connect(AUTH_TOKEN)
        await ws.send(json.dumps({"type": "message", "text": "Tell me something interesting about space."}))

        binary_count = 0
        first_binary_time = None
        last_binary_time = None
        t0 = time.perf_counter()
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(raw, bytes):
                now = time.perf_counter()
                if first_binary_time is None:
                    first_binary_time = now
                last_binary_time = now
                binary_count += 1
            else:
                frame = json.loads(raw)
                if frame.get("type") in ("done", "error"):
                    break

        is_incremental = binary_count > 1
        span_ms = ((last_binary_time - first_binary_time) * 1000) if binary_count > 1 else 0

        report(12, "TTS incremental streaming (not single blob)", is_incremental,
               f"chunks={binary_count}, span={span_ms:.0f}ms")
    except Exception as e:
        report(12, "TTS incremental streaming (not single blob)", False, str(e))
    finally:
        if ws:
            await ws.close()


async def test_tts_latency():
    """First audio chunk within 1.5s of message send. (Requires vLLM + Fish Speech)"""
    ws = None
    try:
        ws = await connect(AUTH_TOKEN)
        t0 = time.perf_counter()
        await ws.send(json.dumps({"type": "message", "text": "Hi there."}))

        first_audio_time = None
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(raw, bytes):
                if first_audio_time is None:
                    first_audio_time = time.perf_counter()
            else:
                frame = json.loads(raw)
                if frame.get("type") in ("done", "error"):
                    break

        if first_audio_time:
            ttfa_ms = (first_audio_time - t0) * 1000
            within_budget = ttfa_ms < 1500
        else:
            ttfa_ms = -1
            within_budget = False

        report(13, "First audio within 1.5s (TTS-03)", within_budget,
               f"TTFA={ttfa_ms:.0f}ms (budget: 1500ms)")
    except Exception as e:
        report(13, "First audio within 1.5s (TTS-03)", False, str(e))
    finally:
        if ws:
            await ws.close()


async def main():
    print("=== Sei Engine Tests ===\n")

    print("--- Offline Tests (no vLLM needed) ---")
    await test_auth_valid_token()
    await test_auth_invalid_token()
    await test_auth_no_token()
    await test_single_session()
    await test_invalid_message_format()
    await test_session_cleanup_on_disconnect()

    if "--online" in sys.argv or "--tts" in sys.argv:
        print("\n--- Online Tests (vLLM required) ---")
        await test_message_protocol()
        await test_sentence_buffering()
        await test_conversation_memory()
    else:
        print("\nSkipping online tests (pass --online to enable, requires vLLM)")

    if "--tts" in sys.argv:
        print("\n--- TTS Tests (vLLM + Fish Speech required) ---")
        await test_tts_binary_frames()
        await test_tts_audio_format()
        await test_tts_incremental_streaming()
        await test_tts_latency()
    else:
        if "--online" not in sys.argv:
            print("\nSkipping online tests (pass --online to enable)")
        print("Skipping TTS tests (pass --tts to enable, requires vLLM + Fish Speech API)")

    print(f"\nResults: {passed}/{total} passed")


if __name__ == "__main__":
    asyncio.run(main())
