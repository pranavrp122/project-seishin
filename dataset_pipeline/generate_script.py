#!/usr/bin/env python3

import json
import os
import sys
import time
import logging
import random
from pathlib import Path

import anthropic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent
OUTPUT_FILE = OUTPUT_DIR / "master_script.jsonl"

CATEGORIES = {
    "A": {"total": 3000, "label": "Casual & Core Affection",
           "tags": ["[happy]", "[excited]", "[chuckle]", "[whisper]", "[sad]",
                    "[warm]", "[gentle]", "[playful]", "[tender]", "[cheerful]"]},
    "B": {"total": 2250, "label": "Technical & Database Reporting",
           "tags": ["[analytical]", "[confident]", "[pause]", "[short pause]",
                    "[emphasis]", "[clear]", "[calm]", "[professional]"]},
    "C": {"total": 2250, "label": "Heavy Acting & Physical Sounds",
           "tags": ["[sarcastic]", "[sigh]", "[inhale]", "[surprised]", "[angry]",
                    "[exhausted]", "[nervous]", "[shouting]", "[laughing]", "[gasp]"]},
}

DURATION_BINS = [
    {"label": "short", "range": (5, 15), "weight": 0.40},
    {"label": "medium", "range": (15, 35), "weight": 0.40},
    {"label": "long", "range": (35, 60), "weight": 0.20},
]

BATCH_SIZE = 50
OPUS_THRESHOLD = 200  # first N per category use Opus
MAX_RETRIES = 5


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

def load_progress() -> dict[str, list[dict]]:
    """Read existing JSONL and return sentences grouped by category."""
    progress: dict[str, list[dict]] = {k: [] for k in CATEGORIES}
    if not OUTPUT_FILE.exists():
        return progress
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                cat = obj.get("category", "")
                if cat in progress:
                    progress[cat].append(obj)
            except json.JSONDecodeError:
                log.warning("Skipping malformed line %d in %s", line_num, OUTPUT_FILE)
    return progress


def next_id(progress: dict[str, list[dict]]) -> int:
    """Return the next available global ID."""
    max_id = 0
    for entries in progress.values():
        for e in entries:
            max_id = max(max_id, e.get("id", 0))
    return max_id + 1


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_system_prompt(category: str, word_range: tuple[int, int]) -> str:
    cat = CATEGORIES[category]
    tags_str = ", ".join(cat["tags"])
    lo, hi = word_range

    return f"""You are a professional TTS script writer generating tagged sentences for voice synthesis training data.

CATEGORY: {category} — {cat["label"]}
AVAILABLE TAGS: {tags_str}
TARGET WORD COUNT: {lo}–{hi} words per sentence (excluding tags)

TAG FORMAT RULES (follow exactly):
- Each tag gets its OWN square brackets: [happy][tired] NOT [happy, tired]
- Maximum 2 tags per sentence
- About 60% of sentences should have 1 tag, about 40% should have 2 tags
- Tags go at the start for whole-sentence emotion: [warm] Hey, how are you?
- For 2-tag sentences, both tags usually go at the start: [happy][excited] That's amazing!
- About 15% of 2-tag sentences should place the second tag mid-sentence for emotion shift: [calm] The data looks fine... [surprised] wait, what is that?
- Physical tags like [sigh], [chuckle], [inhale], [gasp] can appear at start or mid-sentence naturally

STYLE RULES:
- Write natural speech patterns with ellipses (...) for micro-pauses
- Never wrap sentences in quotation marks
- Vary sentence structure and vocabulary heavily — avoid repetitive patterns
- Physical tags should be placed seamlessly mid-thought when appropriate
- Sentences must sound like a real person speaking, not reading from a script
- Use contractions, filler words, natural hesitations where they fit
- Each sentence should feel distinct in rhythm and personality

OUTPUT FORMAT:
Return exactly one JSON object per line. No markdown, no code fences, no extra text.
Each line must be: {{"tag": "<tags>", "text": "<full tagged sentence>"}}

The "tag" field contains only the tag(s) (e.g. "[warm]" or "[happy][excited]").
The "text" field contains the complete sentence including tags in position.

Generate exactly the number of sentences requested. Every line must be valid JSON."""


def build_user_prompt(count: int, word_range: tuple[int, int], category: str) -> str:
    lo, hi = word_range
    return (
        f"Generate {count} unique tagged sentences for category {category}. "
        f"Each sentence body (excluding tags) should be {lo}–{hi} words. "
        f"Output {count} lines, each a JSON object with \"tag\" and \"text\" fields. "
        f"No other text."
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_line(raw: str, category: str) -> dict | None:
    """Parse and validate a single JSON line. Returns dict or None."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if "tag" not in obj or "text" not in obj:
        return None
    tag = obj["tag"].strip()
    text = obj["text"].strip()
    if not tag or not text:
        return None
    if "[" not in tag:
        return None
    return {"tag": tag, "text": text, "category": category}


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------

def append_to_jsonl(records: list[dict]) -> None:
    """Append records to the output file with explicit flush."""
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------------------
# Batch generation
# ---------------------------------------------------------------------------

def generate_batch(
    client: anthropic.Anthropic,
    category: str,
    word_range: tuple[int, int],
    count: int,
    use_opus: bool,
) -> list[dict]:
    """Call Claude API and return validated records (without id/category yet)."""
    if use_opus:
        model = "claude-opus-4-6"
        budget = 10000
    else:
        model = "claude-sonnet-4-6"
        budget = 5000

    system_prompt = build_system_prompt(category, word_range)
    user_prompt = build_user_prompt(count, word_range, category)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=16000,
                thinking={
                    "type": "enabled",
                    "budget_tokens": budget,
                },
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            text_content = ""
            for block in response.content:
                if block.type == "text":
                    text_content += block.text

            results = []
            for line in text_content.splitlines():
                line = line.strip()
                if not line:
                    continue
                rec = validate_line(line, category)
                if rec:
                    results.append(rec)
                else:
                    if line and not line.startswith("{"):
                        continue
                    log.warning("Invalid line skipped: %.80s...", line)

            return results

        except anthropic.RateLimitError:
            wait = 2 ** attempt + random.random()
            log.warning("Rate limited (attempt %d/%d), waiting %.1fs", attempt, MAX_RETRIES, wait)
            time.sleep(wait)
        except anthropic.InternalServerError:
            wait = 2 ** attempt + random.random()
            log.warning("Server error (attempt %d/%d), waiting %.1fs", attempt, MAX_RETRIES, wait)
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                wait = 2 ** attempt + random.random()
                log.warning("API overloaded 529 (attempt %d/%d), waiting %.1fs", attempt, MAX_RETRIES, wait)
                time.sleep(wait)
            else:
                log.error("API error %d: %s", e.status_code, e.message)
                return []
        except anthropic.APIError as e:
            log.error("Unexpected API error: %s", e)
            return []

    log.error("Exhausted retries for batch (category=%s, range=%s–%s)", category, word_range[0], word_range[1])
    return []


# ---------------------------------------------------------------------------
# Category generation plan
# ---------------------------------------------------------------------------

def build_plan(category: str, already_done: int) -> list[dict]:
    """Return a list of batch specs: [{word_range, count, use_opus}, ...]."""
    total = CATEGORIES[category]["total"]
    remaining = total - already_done
    if remaining <= 0:
        return []

    bin_counts = []
    allocated = 0
    for i, b in enumerate(DURATION_BINS):
        if i == len(DURATION_BINS) - 1:
            n = remaining - allocated
        else:
            n = round(remaining * b["weight"])
        bin_counts.append((b["range"], n))
        allocated += n

    batches = []
    generated_so_far = already_done

    for word_range, count_for_bin in bin_counts:
        left = count_for_bin
        while left > 0:
            batch_count = min(BATCH_SIZE, left)
            use_opus = generated_so_far < OPUS_THRESHOLD
            batches.append({
                "word_range": word_range,
                "count": batch_count,
                "use_opus": use_opus,
            })
            generated_so_far += batch_count
            left -= batch_count

    return batches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.error("ANTHROPIC_API_KEY environment variable is not set")
        sys.exit(1)

    client = anthropic.Anthropic()

    progress = load_progress()
    for cat, entries in progress.items():
        total = CATEGORIES[cat]["total"]
        log.info("Loaded %d/%d existing sentences for category %s", len(entries), total, cat)

    current_id = next_id(progress)

    for category in ["A", "B", "C"]:
        cat_done = len(progress[category])
        cat_total = CATEGORIES[category]["total"]

        if cat_done >= cat_total:
            log.info("Category %s already complete (%d/%d), skipping", category, cat_done, cat_total)
            continue

        plan = build_plan(category, cat_done)
        log.info("Category %s: %d sentences remaining, %d batches planned", category, cat_total - cat_done, len(plan))

        batch_num = 0
        for spec in plan:
            batch_num += 1
            model_tag = "opus" if spec["use_opus"] else "sonnet"

            results = generate_batch(
                client,
                category,
                spec["word_range"],
                spec["count"],
                spec["use_opus"],
            )

            if not results:
                log.warning(
                    "Category %s batch %d returned 0 valid sentences (%s, %s–%s words), skipping",
                    category, batch_num, model_tag, spec["word_range"][0], spec["word_range"][1],
                )
                continue

            records = []
            for rec in results:
                rec["id"] = current_id
                rec["category"] = category
                records.append(rec)
                current_id += 1

            append_to_jsonl(records)
            cat_done += len(records)

            pct = (cat_done / cat_total) * 100
            log.info(
                "Category %s: %d/%d (%.1f%%) — batch %d [+%d, %s, %s–%s words]",
                category, cat_done, cat_total, pct, batch_num,
                len(records), model_tag, spec["word_range"][0], spec["word_range"][1],
            )

    final = load_progress()
    grand_total = sum(len(v) for v in final.values())
    log.info("Done. Total sentences: %d / 7500", grand_total)
    for cat in ["A", "B", "C"]:
        log.info("  Category %s: %d / %d", cat, len(final[cat]), CATEGORIES[cat]["total"])


if __name__ == "__main__":
    main()
