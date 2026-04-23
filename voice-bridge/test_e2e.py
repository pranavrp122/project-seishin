#!/usr/bin/env python3
"""
E2E test for voice bridge outbound pipeline.
Generates real speech via Fish Speech, sends it through the bridge,
and verifies: greeting TTS → ASR → LLM → reply TTS.
"""
import asyncio, json, struct, time, sys
import httpx
import msgpack
import websockets

BRIDGE_URL  = "ws://127.0.0.1:7000"
FISH_URL    = "http://127.0.0.1:8080"
SAMPLE_RATE = 16000  # bridge expects 16kHz PCM from client
FRAME_MS    = 20     # 20ms frames

CALL_CTX = {
    "type": "call_context",
    "contact_name": "TestUser",
    "task": "check if they are free this weekend",
    "instructions": (
        "You are Miyo, a friendly personal assistant making a call on behalf of Pranaav. "
        "Your task: find out if the contact is free this weekend. "
        "Be warm, natural, and concise. One or two sentences per turn max."
    ),
}

TEST_PHRASE = "Yes, I'm free this Saturday."


def pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    n = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", n + 36, b"WAVE",
        b"fmt ", 16, 1, 1,
        rate, rate * 2, 2, 16,
        b"data", n,
    )
    return header + pcm


def resample_pcm(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Simple linear resample of mono int16 PCM."""
    import ctypes, array
    samples = array.array("h")
    samples.frombytes(pcm)
    n_src = len(samples)
    n_dst = int(n_src * dst_rate / src_rate)
    out = array.array("h", [0] * n_dst)
    for i in range(n_dst):
        src_i = i * src_rate / dst_rate
        lo = int(src_i)
        hi = min(lo + 1, n_src - 1)
        frac = src_i - lo
        out[i] = int(samples[lo] * (1 - frac) + samples[hi] * frac)
    return bytes(out)


def wav_pcm_bytes(data: bytes) -> tuple[bytes, int]:
    """Extract raw PCM and sample rate from WAV bytes."""
    # Find "fmt " chunk
    i = 12
    rate = 44100
    while i < len(data) - 8:
        tag = data[i:i+4]
        size = struct.unpack_from("<I", data, i+4)[0]
        if tag == b"fmt ":
            rate = struct.unpack_from("<I", data, i + 12)[0]
        elif tag == b"data":
            return data[i+8 : i+8+size], rate
        i += 8 + size
    return b"", rate


async def generate_speech(text: str) -> bytes:
    """Synthesize text via Fish Speech, return 16kHz mono int16 PCM."""
    print(f"  [tts] synthesizing: {text!r}")
    payload = msgpack.packb({
        "text": text,
        "reference_id": "archie",
        "format": "wav",
        "streaming": False,
        "chunk_length": 200,
        "top_p": 0.8,
        "temperature": 0.8,
        "repetition_penalty": 1.1,
        "max_new_tokens": 512,
    })
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.post(
            f"{FISH_URL}/v1/tts",
            content=payload,
            headers={"Content-Type": "application/msgpack"},
        )
        resp.raise_for_status()
        wav = resp.content
    pcm, src_rate = wav_pcm_bytes(wav)
    if not pcm:
        raise RuntimeError("Fish Speech returned empty PCM")
    if src_rate != SAMPLE_RATE:
        pcm = resample_pcm(pcm, src_rate, SAMPLE_RATE)
    print(f"  [tts] got {len(pcm)//2} samples at {SAMPLE_RATE}Hz ({len(pcm)//2/SAMPLE_RATE*1000:.0f}ms)")
    return pcm


async def run_test():
    print("=== Voice Bridge E2E Test ===\n")

    # 1. Generate test speech
    print("[1] Generating test user speech via Fish Speech...")
    user_pcm = await generate_speech(TEST_PHRASE)
    print(f"     OK: {len(user_pcm)} bytes PCM\n")

    # 2. Connect and send call_context
    print("[2] Connecting to bridge...")
    async with websockets.connect(BRIDGE_URL) as ws:
        print("     Connected.\n")

        await ws.send(json.dumps(CALL_CTX))
        print(f"[3] Sent call_context (contact=TestUser)\n")

        # 3. Receive greeting
        print("[4] Waiting for greeting...")
        greeting_text = None
        greeting_audio_bytes = 0
        t_greeting_start = time.perf_counter()

        async def drain_until_speaking_end(timeout=15.0):
            nonlocal greeting_text, greeting_audio_bytes
            deadline = time.perf_counter() + timeout
            speaking = False
            while time.perf_counter() < deadline:
                remaining = deadline - time.perf_counter()
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                if isinstance(msg, bytes):
                    greeting_audio_bytes += len(msg)
                    speaking = True
                elif isinstance(msg, str):
                    data = json.loads(msg)
                    t = data.get("type")
                    if t == "reply" and not greeting_text:
                        greeting_text = data.get("text")
                        print(f"     Greeting text: {greeting_text[:80]}")
                    elif t == "speaking":
                        state = data.get("state")
                        print(f"     speaking:{state}")
                        if state == "end" and speaking:
                            return True
            return False

        got_greeting = await drain_until_speaking_end(timeout=20)
        greeting_ms = (time.perf_counter() - t_greeting_start) * 1000

        if not greeting_text:
            print("  FAIL: no greeting text received")
            return False
        if greeting_audio_bytes < 1000:
            print(f"  FAIL: greeting audio too small ({greeting_audio_bytes} bytes)")
            return False
        print(f"     OK: greeting audio {greeting_audio_bytes//1024}KB in {greeting_ms:.0f}ms\n")

        # 4. Stream user speech as 20ms PCM frames
        print(f"[5] Sending user speech ({TEST_PHRASE!r})...")
        frame_size = SAMPLE_RATE * 2 * FRAME_MS // 1000  # bytes per 20ms frame
        frames_sent = 0
        for offset in range(0, len(user_pcm), frame_size):
            chunk = user_pcm[offset : offset + frame_size]
            if len(chunk) < frame_size:
                chunk = chunk + b"\x00" * (frame_size - len(chunk))
            await ws.send(chunk)
            frames_sent += 1
            await asyncio.sleep(FRAME_MS / 1000)  # real-time pacing

        # Send 500ms of silence to flush VAD
        silence = b"\x00" * frame_size
        for _ in range(25):
            await ws.send(silence)
            await asyncio.sleep(FRAME_MS / 1000)

        print(f"     Sent {frames_sent} speech frames + 500ms silence\n")

        # 5. Wait for reply
        print("[6] Waiting for ASR transcript + AI reply + audio...")
        transcript = None
        reply_text = None
        reply_audio_bytes = 0
        t_reply_start = time.perf_counter()
        deadline = time.perf_counter() + 30

        while time.perf_counter() < deadline:
            remaining = deadline - time.perf_counter()
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if isinstance(msg, bytes):
                reply_audio_bytes += len(msg)
            elif isinstance(msg, str):
                data = json.loads(msg)
                t = data.get("type")
                if t == "transcript":
                    transcript = data.get("text")
                    print(f"     ASR transcript: {transcript!r}")
                elif t == "reply":
                    reply_text = data.get("text")
                    print(f"     AI reply: {reply_text[:80]}")
                elif t == "speaking":
                    state = data.get("state")
                    print(f"     speaking:{state}")
                    if state == "end" and reply_audio_bytes > 0:
                        break

        reply_ms = (time.perf_counter() - t_reply_start) * 1000

    # 6. Report
    print()
    print("=== Results ===")
    passed = True
    def check(label, ok, detail=""):
        nonlocal passed
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}{': ' + detail if detail else ''}")
        if not ok:
            passed = False

    check("Greeting text",    bool(greeting_text))
    check("Greeting audio",   greeting_audio_bytes > 1000,  f"{greeting_audio_bytes//1024}KB")
    check("ASR transcript",   bool(transcript),              repr(transcript))
    check("AI reply text",    bool(reply_text))
    check("Reply audio",      reply_audio_bytes > 1000,      f"{reply_audio_bytes//1024}KB")
    check("Total reply time", reply_ms < 20000,              f"{reply_ms:.0f}ms")

    print()
    print("OVERALL:", "PASS ✓" if passed else "FAIL ✗")
    return passed


if __name__ == "__main__":
    ok = asyncio.run(run_test())
    sys.exit(0 if ok else 1)
