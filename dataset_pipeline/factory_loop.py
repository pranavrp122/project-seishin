#!/home/prana/fish-speech/fish_env/bin/python
"""
factory_loop.py — Batch TTS generation via Fish Audio S2 Pro API.

Reads master_script.jsonl and generates audio/{NNNN}.wav + audio/{NNNN}.lab
pairs using a local Fish S2 Pro server. Supports resume (skips existing pairs),
tag translation, retries with exponential backoff, and graceful Ctrl+C shutdown.
"""

import json
import re
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/prana/fish-speech")

import ormsgpack
import requests
from fish_speech.utils.schema import ServeReferenceAudio, ServeTTSRequest

# ---------------------------------------------------------------------------
# Tag translation matrix — only these tags get expanded; all others pass through
# ---------------------------------------------------------------------------
TAG_TRANSLATIONS: dict[str, str] = {
    "[sarcastic]": "[deadpan][sarcastic][low pitch]",
    "[analytical]": "[articulate][slow]",
}

TAG_RE = re.compile(r"\[[^\]]+\]")

API_URL = "http://127.0.0.1:8080/v1/tts"
REQUEST_TIMEOUT = 120
MAX_RETRIES = 3
BACKOFF_DELAYS = [2, 4, 8]
MIN_WAV_SIZE = 1024  # 1 KB — anything smaller is treated as a failed generation


def translate_tags(text: str) -> str:
    """Replace known tags with their expanded forms; leave all others intact."""

    def _replace(match: re.Match) -> str:
        tag = match.group(0)
        return TAG_TRANSLATIONS.get(tag, tag)

    return TAG_RE.sub(_replace, text)


def load_reference(base_dir: Path) -> tuple[bytes, str]:
    """Load master_seed.wav and master_seed.txt once at startup."""
    wav_path = base_dir / "master_seed.wav"
    txt_path = base_dir / "master_seed.txt"

    if not wav_path.exists():
        print(f"FATAL: Reference audio not found: {wav_path}")
        sys.exit(1)
    if not txt_path.exists():
        print(f"FATAL: Reference text not found: {txt_path}")
        sys.exit(1)

    ref_audio = wav_path.read_bytes()
    ref_text = txt_path.read_text(encoding="utf-8").strip()
    print(f"Loaded reference: {wav_path.name} ({len(ref_audio) / 1024:.1f} KB), "
          f"{len(ref_text)} chars")
    return ref_audio, ref_text


def synthesize(text: str, ref_audio: bytes, ref_text: str) -> bytes | None:
    """POST to Fish S2 Pro API with retries. Returns WAV bytes or None on failure."""
    req = ServeTTSRequest(
        text=text,
        references=[ServeReferenceAudio(audio=ref_audio, text=ref_text)],
        format="wav",
        use_memory_cache="on",
        max_new_tokens=1024,
        temperature=0.8,
        top_p=0.8,
        repetition_penalty=1.1,
    )
    packed = ormsgpack.packb(req, option=ormsgpack.OPT_SERIALIZE_PYDANTIC)

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                API_URL,
                data=packed,
                headers={"content-type": "application/msgpack"},
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code in (500, 503):
                raise requests.exceptions.HTTPError(
                    f"Server error {response.status_code}"
                )

            response.raise_for_status()

            if len(response.content) < MIN_WAV_SIZE:
                raise ValueError(
                    f"WAV too small ({len(response.content)} bytes), likely empty"
                )

            return response.content

        except (requests.exceptions.RequestException, ValueError) as exc:
            delay = BACKOFF_DELAYS[attempt] if attempt < len(BACKOFF_DELAYS) else 8
            if attempt < MAX_RETRIES - 1:
                print(f"  Retry {attempt + 1}/{MAX_RETRIES}: {exc} — "
                      f"waiting {delay}s")
                time.sleep(delay)
            else:
                print(f"  FAILED after {MAX_RETRIES} retries: {exc}")
                return None

    return None


def format_eta(seconds: float) -> str:
    """Format seconds into a human-readable string."""
    if seconds < 0:
        return "???"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def extract_category(entry: dict) -> str:
    """Pull category from JSONL entry, defaulting to '?'."""
    return entry.get("category", "?")


def extract_first_tag(text: str) -> str:
    """Pull the first [tag] from text for display."""
    m = TAG_RE.search(text)
    return m.group(0) if m else ""


def word_count(text: str) -> int:
    """Count words, ignoring tags."""
    cleaned = TAG_RE.sub("", text).strip()
    return len(cleaned.split())


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    script_path = base_dir / "master_script.jsonl"
    audio_dir = base_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    if not script_path.exists():
        print(f"FATAL: {script_path} not found")
        sys.exit(1)

    # Load all lines upfront to get total count
    entries: list[dict] = []
    with script_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"WARNING: Skipping malformed JSONL line {line_num}: {exc}")

    total = len(entries)
    if total == 0:
        print("No entries found in master_script.jsonl")
        sys.exit(0)

    print(f"Loaded {total} entries from {script_path.name}")

    # Load reference audio
    ref_audio, ref_text = load_reference(base_dir)

    # Stats
    success_count = 0
    fail_count = 0
    skip_count = 0
    start_time = time.monotonic()
    processed_count = 0  # samples actually attempted (not skipped)

    # Graceful shutdown
    shutdown_requested = False

    def _signal_handler(signum: int, frame: object) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        print("\n\nShutdown requested — finishing current sample...")

    signal.signal(signal.SIGINT, _signal_handler)

    for idx, entry in enumerate(entries):
        if shutdown_requested:
            break

        sample_id = entry.get("id", idx + 1)
        original_text = entry.get("text", "")
        category = extract_category(entry)
        first_tag = extract_first_tag(original_text)
        n_words = word_count(original_text)

        wav_path = audio_dir / f"{sample_id:04d}.wav"
        lab_path = audio_dir / f"{sample_id:04d}.lab"

        # Resume: skip if both files already exist
        if wav_path.exists() and lab_path.exists():
            skip_count += 1
            continue

        # Translate tags for API (original text preserved for .lab)
        translated_text = translate_tags(original_text)

        # Truncate display text
        display_text = original_text[:50] + ("..." if len(original_text) > 50 else "")

        # Synthesize
        t0 = time.monotonic()
        wav_data = synthesize(translated_text, ref_audio, ref_text)
        elapsed = time.monotonic() - t0
        processed_count += 1

        if wav_data is None:
            fail_count += 1
            print(f"[{sample_id:04d}/{total}] Cat:{category} {first_tag} "
                  f"{display_text} ({n_words} words) -> FAILED [{elapsed:.1f}s]")
        else:
            wav_path.write_bytes(wav_data)
            lab_path.write_text(original_text, encoding="utf-8")
            success_count += 1
            wav_kb = len(wav_data) / 1024
            print(f"[{sample_id:04d}/{total}] Cat:{category} {first_tag} "
                  f"{display_text} ({n_words} words) -> {wav_path.name} "
                  f"({wav_kb:.1f} KB) [{elapsed:.1f}s]")

        # Progress summary every 100 processed samples
        total_done = success_count + fail_count
        if total_done > 0 and total_done % 100 == 0:
            elapsed_total = time.monotonic() - start_time
            avg_per_sample = elapsed_total / processed_count
            remaining = total - skip_count - total_done
            eta = avg_per_sample * remaining
            pct = total_done / total * 100
            print(f"Progress: {total_done}/{total} ({pct:.1f}%) | "
                  f"Success: {success_count} | Failed: {fail_count} | "
                  f"ETA: {format_eta(eta)}")

    # Final stats
    elapsed_total = time.monotonic() - start_time
    print("\n" + "=" * 60)
    print("FACTORY LOOP COMPLETE" if not shutdown_requested else "FACTORY LOOP INTERRUPTED")
    print(f"  Total entries:  {total}")
    print(f"  Skipped (resume): {skip_count}")
    print(f"  Synthesized:    {success_count}")
    print(f"  Failed:         {fail_count}")
    print(f"  Wall time:      {format_eta(elapsed_total)}")
    if processed_count > 0:
        print(f"  Avg per sample: {elapsed_total / processed_count:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
