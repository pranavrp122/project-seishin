"""Verify TTFA: measure exactly when first audio bytes arrive after sending text."""
import time
import requests
import ormsgpack
import numpy as np

API_URL = "http://127.0.0.1:8080/v1/tts"
REFERENCE_ID = "archie"

PROMPTS = [
    "[warm] I left the hallway light on because I know you're coming home late and I didn't want you walking into darkness.",
    "[exhausted] I forgot what day it is. I forgot what I ate for breakfast. I am running on autopilot.",
    "[angry] Don't patronize me with that tone, I can hear it from here!",
    "[tender] Some mornings I wake up and just look at the ceiling feeling truly grateful.",
    "[professional] The lack of structured logging across our services makes incident investigation significantly harder.",
]

SAMPLE_RATE = 44100
WAV_HEADER_SIZE = 44

print("=" * 80)
print("TTFA Verification: streaming=True, sub_chunk_tokens=10 (new default)")
print("Measures: time from HTTP POST to first audio bytes received by client")
print("=" * 80)
print()

for i, text in enumerate(PROMPTS):
    label = text.split("]")[0] + "]"

    payload = {
        "text": text,
        "reference_id": REFERENCE_ID,
        "format": "wav",
        "temperature": 0.7,
        "top_p": 0.8,
        "repetition_penalty": 1.2,
        "max_new_tokens": 1024,
        "chunk_length": 200,
        "streaming": True,
        # sub_chunk_tokens omitted -- testing the NEW DEFAULT (should be 10)
    }

    t_send = time.perf_counter()

    response = requests.post(
        API_URL,
        data=ormsgpack.packb(payload, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
        headers={"Content-Type": "application/msgpack", "Accept": "audio/wav"},
        stream=True,
        timeout=120,
    )

    t_connected = time.perf_counter()

    chunks_received = []
    t_first_audio = None
    first_audio_bytes = 0
    total_audio_bytes = 0

    for chunk in response.iter_content(chunk_size=None):
        t_now = time.perf_counter()
        total_audio_bytes += len(chunk)

        if t_first_audio is None and total_audio_bytes > WAV_HEADER_SIZE:
            t_first_audio = t_now
            first_audio_bytes = total_audio_bytes - WAV_HEADER_SIZE

        chunks_received.append((t_now - t_send, len(chunk)))

    t_done = time.perf_counter()

    # Calculate metrics
    ttfa_ms = (t_first_audio - t_send) * 1000 if t_first_audio else -1
    connect_ms = (t_connected - t_send) * 1000
    total_ms = (t_done - t_send) * 1000
    pcm_bytes = total_audio_bytes - WAV_HEADER_SIZE
    total_samples = pcm_bytes // 2  # int16
    total_audio_dur = total_samples / SAMPLE_RATE
    first_chunk_samples = first_audio_bytes // 2
    first_chunk_dur_ms = (first_chunk_samples / SAMPLE_RATE) * 1000

    print(f"Clip {i+1} {label}")
    print(f"  Text length:        {len(text)} chars")
    print(f"  HTTP connect:       {connect_ms:.0f}ms")
    print(f"  TTFA:               {ttfa_ms:.0f}ms  <-- time until voice starts")
    print(f"  First chunk:        {first_audio_bytes} bytes = {first_chunk_dur_ms:.0f}ms of audio")
    print(f"  Total chunks:       {len(chunks_received)}")
    print(f"  Total audio:        {total_audio_dur:.1f}s")
    print(f"  Total wall time:    {total_ms:.0f}ms")
    print(f"  RTF:                {(total_ms/1000) / total_audio_dur:.2f}x")
    print()

print("=" * 80)
print("What TTFA means in your LLM->TTS pipeline:")
print("  1. LLM finishes generating text")
print("  2. Your app sends text to TTS via HTTP POST (streaming=True)")
print("  3. TTFA = time from step 2 until first audio bytes arrive")
print("  4. Your app can start playing audio immediately at step 3")
print("  5. Remaining audio streams in while playback continues")
print("=" * 80)
