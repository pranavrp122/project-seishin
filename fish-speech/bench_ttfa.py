"""Measure TTFA for each clip using streaming mode."""
import time
import requests
import ormsgpack

API_URL = "http://127.0.0.1:8080/v1/tts"
REFERENCE_ID = "archie"  # Pre-registered reference, avoids re-encoding VQ each request

PROMPTS = [
    ("[warm] I left the hallway light on because I know you're coming home late and I didn't want you walking into darkness.", "01_warm"),
    ("[exhausted] I forgot what day it is. I forgot what I ate for breakfast. I am running on autopilot. The autopilot is also exhausted and requesting permission to land immediately.", "02_exhausted"),
    ("[angry] Don't patronize me with that tone, I can hear it from here!", "03_angry"),
    ("[tender] Some mornings I wake up and just look at the ceiling feeling truly grateful that my life has you woven through every part.", "04_tender"),
    ("[professional] The lack of structured logging across our services makes incident investigation significantly harder. It is adding at least twenty minutes to our mean time to detect.", "05_professional"),
]

print(f"{'Clip':<20} {'Chars':>5} {'TTFA':>8} {'Total':>8} {'Audio':>7}")
print("-" * 55)

for text, name in PROMPTS:
    payload = {
        "text": text,
        "reference_id": REFERENCE_ID,
        "format": "wav",
        "max_new_tokens": 1024,
        "chunk_length": 200,
        "streaming": True,
    }

    t0 = time.perf_counter()
    t_first = None
    total_bytes = 0
    header_seen = False

    resp = requests.post(
        API_URL,
        data=ormsgpack.packb(payload, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
        headers={"Content-Type": "application/msgpack", "Accept": "audio/wav"},
        stream=True,
        timeout=120,
    )

    for chunk in resp.iter_content(chunk_size=4096):
        if not header_seen and len(chunk) >= 44:
            header_seen = True
            audio_part = chunk[44:]
            if audio_part and t_first is None:
                t_first = time.perf_counter()
            total_bytes += len(audio_part)
            continue
        if t_first is None and chunk:
            t_first = time.perf_counter()
        total_bytes += len(chunk)

    t_end = time.perf_counter()
    ttfa = (t_first - t0) * 1000 if t_first else (t_end - t0) * 1000
    total = (t_end - t0) * 1000
    audio_sec = (total_bytes / 2) / 44100

    print(f"{name:<20} {len(text):>5} {ttfa:>6.0f}ms {total:>6.0f}ms {audio_sec:>5.1f}s")
