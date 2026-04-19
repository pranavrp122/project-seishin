#!/usr/bin/env python3
"""Sei Engine - Async WebSocket server bridging clients to Gemma 4 LLM.

Streams LLM responses as sentence-boundary JSON frames over WebSocket.
Auth via Bearer token, single-session enforcement, conversation memory.

Usage:
    SEI_AUTH_TOKEN=your-secret python scripts/sei_engine.py
"""
import asyncio
import hmac
import json
import os
import sys
import time
from collections import deque
from http import HTTPStatus
from collections import defaultdict
from collections.abc import AsyncGenerator
from pathlib import Path

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
import httpx
import ormsgpack

import re

from system_prompts import SYSTEM_PROMPT, SEED_HISTORY
from intent_classifier import classify_intent
from session_cache import SessionCache, SessionMemory, SEI_DATA_DIR, JsonFileBackend, deserialize_into_cache
from op_spec import generate_op_spec
from cache_executor import CacheExecutor, _fuzzy_match_column, merge_compatible_reports
from text_utils import _normalize_datetime
from memory_ops import execute_op, aggregate_multi, OpSpecError
from fastpath_patterns import is_fastpath_chat


# --- Log redaction (D-20-08.5) ---
_EMAIL_RE = re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b')
_PHONE_RE = re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b')


def _redact_log(text: str, max_len: int = 50) -> str:
    """Truncate and redact PII for logging."""
    redacted = _EMAIL_RE.sub('[REDACTED]', text)
    redacted = _PHONE_RE.sub('[REDACTED]', redacted)
    if len(redacted) > max_len:
        return f"{redacted[:max_len]}... ({len(text)} chars)"
    return redacted


# --- .env loading (D-20-08.1) ---
def _load_env_file(path: Path) -> None:
    """Parse KEY=VALUE lines from a .env file into os.environ (setdefault)."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


# Load .env: prefer ~/.sei/.env, fallback to repo .env in dev mode
_sei_env = SEI_DATA_DIR / ".env"
if _sei_env.exists():
    _load_env_file(_sei_env)
elif os.environ.get("SEI_DEV_MODE") == "1":
    _repo_env = Path(__file__).parent.parent / ".env"
    if _repo_env.exists():
        _load_env_file(_repo_env)


# --- Configuration ---
AUTH_TOKEN = os.environ.get("SEI_AUTH_TOKEN", "")
if not AUTH_TOKEN:
    if os.environ.get("SEI_DEV_MODE") == "1":
        import secrets
        AUTH_TOKEN = secrets.token_urlsafe(32)
        print(f"DEV MODE: Generated ephemeral auth token (use SEI_AUTH_TOKEN to set a stable one)")
    else:
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

# D-20-08.1: Fail-loud if REPORT_API_KEY is missing
if not os.environ.get("REPORT_API_KEY"):
    print("FATAL: REPORT_API_KEY not set. Set in ~/.sei/.env or environment.")
    sys.exit(1)

# D-20-08.2: Dev-mode bind guard — refuse non-loopback bind with dev token
if os.environ.get("SEI_DEV_MODE") == "1" and BIND_ADDR != "127.0.0.1":
    print(f"FATAL: SEI_DEV_MODE=1 requires SEI_BIND=127.0.0.1, got {BIND_ADDR}")
    sys.exit(1)

# Text mode: skip TTS entirely, responses show as text only
TEXT_MODE = os.environ.get("SEI_TEXT_MODE", "0") == "1"


class TurnCancelScope:
    """Per-turn cancellation scope (D-19). All long-running awaits in a turn
    check this scope and abort cleanly on cancel."""

    def __init__(self):
        self._cancelled = False
        self._tasks: list[asyncio.Task] = []

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self):
        """Cancel all tracked tasks in this scope."""
        self._cancelled = True
        for task in self._tasks:
            if not task.done():
                task.cancel()

    def track(self, task: asyncio.Task) -> asyncio.Task:
        """Register a task for cancellation."""
        self._tasks.append(task)
        return task

    async def run(self, coro):
        """Run a coroutine within this cancel scope. Raises asyncio.CancelledError if cancelled."""
        if self._cancelled:
            raise asyncio.CancelledError("Turn cancelled")
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        try:
            return await task
        except asyncio.CancelledError:
            raise


async def handle_llm_response_text_only(ws, messages: list[dict], cancel_event: asyncio.Event) -> str:
    """Get full LLM response text without sending to WebSocket/TTS. For internal use."""
    reply_parts = []
    async for token in stream_llm(messages, cancel_event):
        reply_parts.append(token)
        if cancel_event.is_set():
            break
    return "".join(reply_parts).strip()


async def _buffer_llm_tokens(messages: list[dict], cancel_event: asyncio.Event) -> str:
    """Stream LLM tokens into a buffer without sending anywhere. Returns full text."""
    parts = []
    async for token in stream_llm(messages, cancel_event):
        parts.append(token)
        if cancel_event.is_set():
            break
    return "".join(parts).strip()


def _build_ground_truth_block(res: dict, max_rows: int = 40) -> tuple[str, set, set]:
    """Compact JSON table from report result. Returns (text_block, number_set, name_set).

    number_set: every numeric value present (as str, normalized) — used to detect
    hallucinated counts/values in the LLM's spoken reply.
    name_set: every string cell value (lowercased) — used to detect fabricated
    entity names.
    """
    results = res.get("results") or []
    rows = results[:max_rows]
    cols: list[str] = []
    if rows and isinstance(rows[0], dict):
        cols = list(rows[0].keys())
    numbers: set = set()
    names: set = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        for v in r.values():
            if isinstance(v, (int, float)):
                numbers.add(str(v))
                try:
                    numbers.add(str(int(v)))
                except Exception:
                    pass
            elif isinstance(v, str) and v.strip():
                if re.fullmatch(r"-?\d+(\.\d+)?", v.strip()):
                    numbers.add(v.strip())
                    try:
                        numbers.add(str(int(float(v))))
                    except Exception:
                        pass
                else:
                    names.add(v.strip().lower())
    numbers.add(str(res.get("row_count", len(results))))
    try:
        text = json.dumps({"columns": cols, "row_count": res.get("row_count", len(results)), "rows": rows}, default=str)[:4000]
    except Exception:
        text = str(rows)[:4000]
    return text, numbers, names


_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_WORD_NUM = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
    "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
    "hundred": "100", "thousand": "1000",
}


def _extract_claimed_numbers(text: str) -> set:
    """Extract digit and spelled-out numbers from LLM reply."""
    claims: set = set()
    for m in _NUM_RE.findall(text):
        claims.add(m)
        try:
            claims.add(str(int(float(m))))
        except Exception:
            pass
    low = text.lower()
    for word, digit in _WORD_NUM.items():
        if re.search(rf"\b{word}\b", low):
            claims.add(digit)
    return claims


def _validate_spoken_against_truth(spoken: str, numbers: set, prose_summary: str) -> list[str]:
    """Return list of claimed numbers present in spoken but absent from ground truth.

    We're permissive: only flag numbers that appear nowhere in the structured rows
    AND nowhere in the prose summary (which may contain aggregates/counts the LLM
    can legitimately restate).
    """
    claimed = _extract_claimed_numbers(spoken)
    prose_nums = _extract_claimed_numbers(prose_summary or "")
    bad = []
    for n in claimed:
        if n in {"1", "2"}:  # ignore trivial referential numbers ("one more", etc.)
            continue
        if n in numbers or n in prose_nums:
            continue
        bad.append(n)
    return bad


async def deliver_report_result(websocket, report_task: asyncio.Task, history: list, tts_client: httpx.AsyncClient, query: str = "", session_cache=None, cache_kind: str = "base", session_memory=None, parent_report_id: str | None = None, origin_op: str = "fetch", derivation_summary: str = "") -> bool:
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
        "source": "fetch",
    }))

    # Cache report data for follow-up operations via SessionMemory facade.
    # kind tags whether it's a fresh base fetch or a derived fallback result.
    # Follow-up target resolution uses session_memory.resolve_target().
    if res.get("results") and session_memory is not None:
        topic_words = [w for w in query.lower().split() if len(w) > 3 and w not in {"data", "show", "from", "with", "that", "this", "what", "about", "report", "pull", "give", "tell"}][:3]
        topic = " ".join(topic_words) if topic_words else query[:30]
        report_id = session_memory.record(
            res, kind=cache_kind, parent_id=parent_report_id,
            origin_op=origin_op, topic=topic, query=query,
            sql=res.get("sql") or res.get("sql_text") or "",
            derivation_summary=derivation_summary,
        )
        print(f"  Cached report {report_id} kind={cache_kind} ({len(res.get('results', []))} rows)")
    elif res.get("results") and session_cache is not None:
        # Legacy fallback for callers not yet passing session_memory
        report_id = session_cache.store(
            res,
            query=query,
            sql=res.get("sql") or res.get("sql_text") or "",
            kind=cache_kind,
        )
        print(f"  Cached report {report_id} kind={cache_kind} ({len(res.get('results', []))} rows)")

    if raw_summary:
        # Build structured ground_truth alongside the prose summary.
        gt_text, gt_numbers, gt_names = _build_ground_truth_block(res)
        base_prompt = (
            f"[INTERNAL: Report complete ({res.get('row_count', 0)} rows).\n"
            f"<ground_truth_rows>{gt_text}</ground_truth_rows>\n"
            f"<data_summary>{raw_summary}</data_summary>\n\n"
            "STRICT RULES:\n"
            "1. <ground_truth_rows> and <data_summary> are the ONLY sources of truth. Speak nothing that isn't literally in them.\n"
            "2. Never invent or estimate counts, names, numbers, or categories. Every number/name you say must appear in ground_truth_rows or data_summary.\n"
            "3. Do NOT count or tally anything yourself — if the summary doesn't already state a count, don't guess one.\n"
            "4. Do NOT list all rows. The user can see them on screen.\n"
            "5. Give ONE spoken takeaway in 1-2 sentences — the headline point the summary already makes.\n"
            "6. If the summary is empty or unclear, say so honestly rather than fabricating.]"
        )
        intro_messages = list(history) + [{"role": "user", "content": base_prompt}]
        _ce = asyncio.Event()
        spoken = await handle_llm_response_text_only(websocket, intro_messages, _ce)

        # Post-generation validation: check claimed numbers against ground truth.
        if spoken:
            bad = _validate_spoken_against_truth(spoken, gt_numbers, raw_summary)
            if bad:
                print(f"  [hallucination] retry — claimed numbers not in ground_truth: {bad}")
                retry_prompt = base_prompt + (
                    f"\n\n[REGEN: Your previous reply contained numbers {bad} that are NOT in "
                    f"ground_truth_rows or data_summary. Do not state them. Speak ONLY values "
                    f"literally present above. Keep it to 1-2 sentences.]"
                )
                intro_messages[-1] = {"role": "user", "content": retry_prompt}
                _ce2 = asyncio.Event()
                retry_text = await handle_llm_response_text_only(websocket, intro_messages, _ce2)
                if retry_text:
                    still_bad = _validate_spoken_against_truth(retry_text, gt_numbers, raw_summary)
                    if still_bad:
                        print(f"  [hallucination] retry still bad: {still_bad} — using summary verbatim")
                        spoken = raw_summary
                    else:
                        spoken = retry_text
                else:
                    spoken = raw_summary
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


_REPORT_API_DEADLINE = float(os.environ.get("SEI_REPORT_DEADLINE", "90"))


async def call_report_api(user_request: str) -> dict:
    """POST user request to the report generator with retry + deadline (D-20-04)."""
    user_request = user_request[:1000]
    headers = {"X-API-Key": REPORT_API_KEY} if REPORT_API_KEY else {}
    delays = [0.5, 1.0]
    deadline = time.monotonic() + _REPORT_API_DEADLINE
    last_exc = None
    for attempt in range(3):  # initial + 2 retries
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{REPORT_API_URL}/report",
                    json={"user_request": user_request},
                    headers=headers,
                    timeout=httpx.Timeout(connect=2.0, read=min(remaining, _REPORT_API_DEADLINE - 2), write=2.0, pool=2.0),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt < len(delays):
                await asyncio.sleep(delays[attempt])
    raise last_exc or TimeoutError(f"Report API: {_REPORT_API_DEADLINE}s deadline exceeded")


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
_RATE_LIMIT_MAX_IPS = 10000


class MessageRateLimiter:
    """Per-connection message rate limiter: max_messages per window_seconds (D-20-08.3)."""

    def __init__(self, max_messages: int = 60, window_seconds: float = 60.0):
        self._max = max_messages
        self._window = window_seconds
        self._timestamps: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._timestamps and now - self._timestamps[0] > self._window:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._max:
            return False
        self._timestamps.append(now)
        return True


# --- Global state ---
active_ws = None


async def process_request(connection, request):
    """Validate Bearer token and enforce single session before WebSocket upgrade."""
    global active_ws

    # Per-IP sliding window rate limit
    ip = connection.remote_address[0]
    now = time.time()

    # Evict stale IPs to prevent unbounded growth (CR-01)
    if len(_rate_limit_window) > _RATE_LIMIT_MAX_IPS:
        cutoff = now - _RATE_LIMIT_SECONDS
        stale = [k for k, ts in _rate_limit_window.items() if not ts or ts[-1] < cutoff]
        for k in stale:
            del _rate_limit_window[k]

    # Exempt loopback from connection rate limiting (dev/test scenarios hit this fast)
    if ip not in ("127.0.0.1", "::1"):
        window = _rate_limit_window[ip]
        _rate_limit_window[ip] = [t for t in window if now - t < _RATE_LIMIT_SECONDS]
        _rate_limit_window[ip].append(now)
        if len(_rate_limit_window[ip]) > _RATE_LIMIT_MAX:
            return connection.respond(HTTPStatus.TOO_MANY_REQUESTS, "Rate limit exceeded\n")

    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {AUTH_TOKEN}".encode()
    provided = auth.encode() if auth else b""
    if not hmac.compare_digest(expected, provided):
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


_HISTORY_FIXED_PREFIX = 3       # system prompt + 2 seed turns
_HISTORY_MAX_TOKENS = 100_000   # compact when estimated tokens exceed this
_HISTORY_KEEP_TURNS = 15        # always keep this many recent turns intact after compaction

def _estimate_tokens(history: list[dict]) -> int:
    """Rough token estimate: 1 token ≈ 4 chars."""
    return sum(len(m.get("content", "")) for m in history) // 4

def _compact_history(history: list[dict]) -> None:
    """When estimated context tokens exceed budget, summarize old turns into a single
    system block and keep the last _HISTORY_KEEP_TURNS turns intact."""
    if _estimate_tokens(history) <= _HISTORY_MAX_TOKENS:
        return

    prefix = history[:_HISTORY_FIXED_PREFIX]
    rest = history[_HISTORY_FIXED_PREFIX:]
    keep_n = _HISTORY_KEEP_TURNS * 2  # user + assistant per turn

    if len(rest) <= keep_n:
        return  # nothing old enough to compact

    old, recent = rest[:-keep_n], rest[-keep_n:]

    lines = []
    for m in old:
        content = m.get("content", "")
        if content.startswith("[INTERNAL"):
            continue
        role = "User" if m["role"] == "user" else "Miyako"
        lines.append(f"- {role}: {content[:120]}")

    summary = (
        "[Earlier conversation compacted for context budget. Summary:\n"
        + "\n".join(lines[:30])
        + "\nRecent conversation follows.]"
    )

    history[:] = prefix + [{"role": "system", "content": summary}] + recent
    print(f"  [context.compact] compacted {len(old)} old messages, kept {len(recent)} recent")


_HOLLOW_PATTERNS = re.compile(
    r"^(got it|sure thing|on it|let me check|lemme check|let me see|lemme see|"
    r"hold on|one moment|just a moment|checking|looking into|i'll check|"
    r"oops|my bad|sorry about that|wait|hmm)[.!,\s]*$",
    re.IGNORECASE,
)

def is_quality_response(reply: str) -> bool:
    """Check if LLM reply meets minimum quality bar — not a hollow ack."""
    if not reply or len(reply) < 10:
        return False
    # Reject if the entire reply is a hollow acknowledgment with no data content
    stripped = reply.strip().rstrip(".!?,")
    if _HOLLOW_PATTERNS.match(stripped):
        return False
    return True


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
                await ws.send(bytes(44100 * 150 // 1000 * 2))  # 150ms silence at 44.1kHz PCM16 mono
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
        print(f"  {label}: {elapsed:.0f}ms -> '{_redact_log(text)}'", flush=True)
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
            session_cache.store({"results": chain_result["rows"]}, query=report_query, sql=target["sql"], kind="derived")
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



async def handler(websocket):
    """Handle a single WebSocket client session with barge-in support."""
    global active_ws
    active_ws = websocket  # Set here where finally block guarantees cleanup
    history = build_initial_messages()
    session_cache = SessionCache(ttl_seconds=600)
    session_memory = SessionMemory(session_cache)
    msg_limiter = MessageRateLimiter()  # D-20-08.3: per-connection 60 msg/min

    # D-20-09: Persistence disabled — per-session memory only until DB+client setup
    # session_cache.attach_persistence(JsonFileBackend())

    print(f"Client connected: {websocket.remote_address}")

    try:
        async with httpx.AsyncClient() as tts_client:
            pending_msg = None  # Buffered message from stop-listener
            pending_overlap_query = None  # Held query awaiting user confirmation
            active_report_task = None   # Background asyncio.Task for call_report_api
            active_report_query = ""    # The original user query being reported on
            active_report_kind = "base"  # "base" for fresh new_data_request; "derived" for fallback-path API calls inside a follow-up
            active_report_parent_id: str | None = None  # D-15: parent lineage for fallback fetches
            active_report_derivation: str = ""          # D-15: derivation summary for fallback fetches
            audio_buf = bytearray()  # Streaming PCM accumulation buffer
            is_accumulating = False
            asr_task = None
            asr_stop = None
            asr_result = {"text": "", "len": 0}
            undo_stack: list[dict] = []  # D-03: last 5 ops
            last_intent_result: dict | None = None  # D-05: stored for op_chain after delivery
            turn_scope = None  # D-19: per-turn cancellation scope (WR-01: init before loop)
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
                            await deliver_report_result(websocket, active_report_task, history, tts_client, active_report_query, session_cache=session_cache, cache_kind=active_report_kind, session_memory=session_memory, parent_report_id=active_report_parent_id, origin_op="fetch", derivation_summary=active_report_derivation)
                            if last_intent_result:
                                await _apply_op_chain(websocket, last_intent_result, session_cache, active_report_query)
                                last_intent_result = None
                            active_report_task = None
                            active_report_query = ""
                            active_report_kind = "base"
                            active_report_parent_id = None
                            active_report_derivation = ""
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
                                print(f"  ASR-cached: '{_redact_log(text)}' (tail {skip_pct:.0f}% unprocessed)", flush=True)
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

                # D-20-08.3: Per-connection message rate limit
                if not msg_limiter.allow():
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Rate limit exceeded. Max 60 messages per minute.",
                    }))
                    continue

                if msg.get("type") != "message" or not msg.get("text"):
                    # D-19: Stop message cancels any in-flight turn scope
                    if msg.get("type") == "stop" and turn_scope is not None:
                        print(f"  [cancel] Stop received, cancelling turn scope at {time.monotonic():.1f}")
                        turn_scope.cancel()
                        # D-20: Cache is consistent — session_memory.record() is synchronous.
                        # If cancel fires before record(), no partial write exists.
                        # If cancel fires after record(), the record is complete.
                        await websocket.send(json.dumps({"type": "cancelled"}))
                    elif msg.get("type") not in ("speech_start", "speech_end", "stop"):
                        await websocket.send(json.dumps({"type": "error", "message": "Expected {type: message, text: ...}"}))
                    continue

                user_text = msg["text"].strip()
                if not user_text:
                    continue

                # D-08: Normalize relative date references before any classification
                user_text = _normalize_datetime(user_text)

                # D-19: Per-turn cancellation scope for cancel-anywhere semantics.
                turn_scope = TurnCancelScope()

                # --- Overlap confirmation handling ---
                skip_classification = False
                speculative_chat_task = None
                speculative_cancel = asyncio.Event()
                opening_phrase = ""

                if pending_overlap_query is not None:
                    overlap_intent = await classify_intent(
                        user_text, history, bool(session_cache.all_reports()),
                        last_target=session_cache.get_latest(),
                    )
                    if overlap_intent["intent"] == "confirm":
                        pending_overlap_query = None
                        history.append({"role": "user", "content": user_text})
                        print(f"  User confirmed overlap -> follow_up_on_previous")
                        intent = "follow_up_on_previous"
                        confidence = 0.95
                        data_query = None
                        skip_classification = True
                    else:
                        saved_query = pending_overlap_query
                        pending_overlap_query = None
                        active_report_query = saved_query
                        active_report_task = turn_scope.track(asyncio.create_task(call_report_api(saved_query)))
                        # Fall through to normal intent classification for current message

                if not skip_classification:
                    _compact_history(history)
                    history.append({"role": "user", "content": user_text})
                print(f"  User: {_redact_log(user_text)}")

                if not skip_classification:
                    # --- D-20-01: Fast-path for small-talk — skip classification entirely ---
                    has_reports = bool(session_cache.all_reports()) or (
                        active_report_task is not None and not active_report_task.done()
                    )
                    if (
                        pending_overlap_query is None
                        and not (history and history[-1].get("role") == "assistant"
                                 and history[-1].get("content", "").rstrip().endswith("?"))
                        and is_fastpath_chat(user_text)
                    ):
                        intent = "normal_chat"
                        confidence = 1.0
                        data_query = None
                        opening_phrase = ""
                        skip_classification = True
                        print(f"[fastpath] Matched: {_redact_log(user_text)}")

                if not skip_classification:
                    # --- Intent classification (D-20-03: always speculate chat, never op_spec) ---
                    speculative_cancel = asyncio.Event()
                    speculative_chat_task = asyncio.create_task(
                        _buffer_llm_tokens(history, speculative_cancel)
                    )

                    intent_result = await classify_intent(
                        user_text, history, has_reports,
                        last_target=session_cache.get_latest(),
                    )
                    intent = intent_result["intent"]
                    confidence = intent_result["confidence"]
                    data_query = intent_result["data_query"]
                    opening_phrase = intent_result.get("opening_phrase", "")
                    last_intent_result = intent_result  # D-05: store for op_chain after delivery

                    # Cancel speculative chat buffer if intent won't use it.
                    # confirm/cancel fall through to normal_chat so they keep it.
                    if speculative_chat_task is not None and intent not in ("normal_chat", "confirm", "cancel"):
                        speculative_cancel.set()
                        speculative_chat_task.cancel()
                        speculative_chat_task = None
                else:
                    # Fast-path or overlap-confirm: still fire speculative chat for the reply
                    if speculative_chat_task is None:
                        speculative_cancel = asyncio.Event()
                        speculative_chat_task = asyncio.create_task(
                            _buffer_llm_tokens(history, speculative_cancel)
                        )

                # Flush LLM-generated opening (unique per request) for non-chat intents
                if opening_phrase and intent not in ("normal_chat", "confirm", "cancel"):
                    await websocket.send(json.dumps({"type": "sentence", "text": opening_phrase}))
                    _op_ce = asyncio.Event()
                    await tts_full_response(websocket, opening_phrase, tts_client, _op_ce)

                # Always show classified intent in chat for testing visibility
                await websocket.send(json.dumps({
                    "type": "sentence",
                    "text": f"(intent: {intent}, confidence: {confidence:.2f})"
                }))

                if intent == "new_data_request" and confidence >= 0.6:
                    # Fire report immediately — no confirmation gate
                    query = data_query or user_text

                    # D-14-06: Zero-LLM semantic dedup fast-path before D-18 LLM check
                    semantic_match = session_memory.find_semantic_duplicate(query)
                    if semantic_match:
                        print(f"  [memory.dedup] semantic reuse: {semantic_match['report_id']}")
                        await websocket.send(json.dumps({
                            "type": "report_log",
                            "query": query,
                            "sql": semantic_match.get("sql", ""),
                            "row_count": semantic_match["row_count"],
                            "results": semantic_match["rows"],
                            "summary": f"Using cached data ({semantic_match['row_count']} rows) from earlier query.",
                            "claude_interactions": [],
                            "dashboard_b64": "",
                        }))
                        reuse_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                f"[INTERNAL: You already have this data cached ({semantic_match['row_count']} rows "
                                f"from: {semantic_match.get('query', '')[:60]}). Let the user know you're using "
                                "the data you already pulled. One casual sentence, stay in character.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        reuse_reply = await handle_llm_response(websocket, reuse_messages, tts_client, _ce)
                        if reuse_reply:
                            history.append({"role": "assistant", "content": reuse_reply})
                        continue

                    # D-18: Check for compatible cached base before firing fresh API call
                    compatible_base = await session_memory.check_compatible_base(query)
                    if compatible_base:
                        print(f"  D-18 base reuse: delivering cached {compatible_base['report_id']} "
                              f"({compatible_base['row_count']} rows) instead of fresh API call")
                        await websocket.send(json.dumps({
                            "type": "report_log",
                            "query": query,
                            "sql": compatible_base.get("sql", ""),
                            "row_count": compatible_base["row_count"],
                            "results": compatible_base["rows"],
                            "summary": f"Using cached data ({compatible_base['row_count']} rows) from earlier query.",
                            "claude_interactions": [],
                            "dashboard_b64": "",
                        }))
                        # Voice a natural acknowledgment
                        reuse_messages = list(history) + [{
                            "role": "user",
                            "content": (
                                f"[INTERNAL: You already have this data cached ({compatible_base['row_count']} rows "
                                f"from: {compatible_base.get('query', '')[:60]}). Let the user know you're using "
                                "the data you already pulled. One casual sentence, stay in character.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        reuse_reply = await handle_llm_response(websocket, reuse_messages, tts_client, _ce)
                        if reuse_reply:
                            history.append({"role": "assistant", "content": reuse_reply})
                        continue

                    active_report_query = query
                    active_report_task = turn_scope.track(asyncio.create_task(call_report_api(query)))
                    # D-20-02: opening_phrase already flushed to TTS above (replaces old ack LLM call)
                    if opening_phrase:
                        history.append({"role": "assistant", "content": opening_phrase})
                    continue

                elif intent == "new_data_request" and confidence < 0.6:
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
                    # D-20-03: op_spec fires sequentially after classification (never speculative)
                    op_spec_result = await generate_op_spec(
                        user_text,
                        session_memory.summary_for_context(),
                        merge_compatible_reports(session_cache.base_reports())
                        or session_cache.get_latest_base()
                        or session_cache.get_latest(),
                    )

                    # LLM parse error — try answering from cached data before re-firing
                    if op_spec_result.get("op_type") == "_error":
                        _error_target = await session_memory.resolve_target(user_text)
                        _error_parent_id = _error_target["report_id"] if _error_target else None

                        # If cached rows exist, attempt a direct data-grounded answer first.
                        # This handles vague follow-ups like "which one" / "that one" without
                        # needing a round-trip to the Report API.
                        if _error_target and _error_target.get("rows"):
                            _ep_rows = _error_target["rows"][:15]
                            _ep_text = json.dumps(_ep_rows, default=str)[:2000]
                            _ep_n = _error_target.get("row_count", len(_ep_rows))
                            direct_messages = list(history[:-1]) + [{
                                "role": "user",
                                "content": (
                                    f"{user_text}\n\n"
                                    f"[Data ({_ep_n} rows):\n<data>{_ep_text}</data>\n"
                                    "Answer the question above from this data. 1-2 sentences.]"
                                ),
                            }]
                            _ce = asyncio.Event()
                            direct_reply = await handle_llm_response_text_only(websocket, direct_messages, _ce)
                            if direct_reply and is_quality_response(direct_reply) and "[NEED_ALL_ROWS]" not in direct_reply:
                                history.append({"role": "assistant", "content": direct_reply})
                                await websocket.send(json.dumps({"type": "sentence", "text": direct_reply}))
                                _ce2 = asyncio.Event()
                                await tts_full_response(websocket, direct_reply, tts_client, _ce2)
                                await websocket.send(json.dumps({"type": "done"}))
                                continue

                        # No usable cached data — voice a hint then fire fresh API
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
                        active_report_kind = "derived"
                        active_report_task = turn_scope.track(asyncio.create_task(call_report_api(query)))
                        active_report_parent_id = _error_parent_id
                        active_report_derivation = "re-fetched after op parse error"
                        continue

                    # Resolve target report via SessionMemory facade (D-14).
                    # Priority: explicit report_id from op_spec > merge_cached >
                    # session_memory.resolve_target() (LLM-driven).
                    if op_spec_result.get("merge_cached"):
                        bases = session_cache.base_reports()
                        target_report = (
                            merge_compatible_reports(bases)
                            or session_cache.get_latest_base()
                            or session_cache.get_latest()
                        )
                    else:
                        explicit = session_cache.get(op_spec_result.get("report_id")) if op_spec_result.get("report_id") else None
                        if explicit:
                            target_report = explicit
                        else:
                            referenced_col = op_spec_result.get("column")
                            referenced_cols_pre = op_spec_result.get("columns") or []
                            all_referenced_pre = ([referenced_col] if referenced_col else []) + referenced_cols_pre
                            _op_ctx = {"op_type": op_spec_result.get("op_type"), "columns": all_referenced_pre} if all_referenced_pre else None
                            target_report = await session_memory.resolve_target(user_text, op_context=_op_ctx)
                    all_cached = session_cache.all_reports()
                    print(f"  Follow-up target: {target_report.get('row_count') if target_report else 'None'} rows kind={target_report.get('kind') if target_report else '-'} topic={target_report.get('query', '')[:40] if target_report else '-'!r} (cached={len(all_cached)})")
                    if target_report is not None and target_report.get("kind") == "base":
                        print(f"  [memory.cache_hit] target={target_report['report_id']} reused_rows={target_report['row_count']} -- skipped fetch")

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
                        active_report_task = turn_scope.track(asyncio.create_task(call_report_api(query)))
                        continue

                    # FOLLOW-05 + D-02: Validate referenced columns with fuzzy matching
                    referenced_col = op_spec_result.get("column")
                    referenced_cols = op_spec_result.get("columns") or []
                    all_referenced = ([referenced_col] if referenced_col else []) + referenced_cols

                    # Resolve columns via fuzzy matching before declaring them missing
                    _cols = target_report["columns"]
                    available_cols = list(_cols.keys()) if isinstance(_cols, dict) else list(_cols)
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
                        # D-14-03: Lineage climb — walk parent chain for missing columns
                        chain = session_memory.lineage(target_report["report_id"])
                        climb_resolved = False
                        for ancestor in chain[1:]:  # skip current report
                            ancestor_cols = list(ancestor.get("columns", {}).keys())
                            if all(c in ancestor_cols or _fuzzy_match_column(c, ancestor_cols) for c in missing_cols):
                                # Re-resolve fuzzy cols against ancestor
                                for c in missing_cols:
                                    if c in ancestor["columns"]:
                                        resolved_cols[c] = c
                                    else:
                                        resolved_cols[c] = _fuzzy_match_column(c, ancestor_cols)
                                if op_spec_result.get("column") in resolved_cols:
                                    op_spec_result["column"] = resolved_cols[op_spec_result["column"]]
                                if op_spec_result.get("columns"):
                                    op_spec_result["columns"] = [resolved_cols.get(c, c) for c in op_spec_result["columns"]]
                                try:
                                    climb_result = execute_op(ancestor["rows"], op_spec_result)
                                    if climb_result:
                                        print(f"  [memory.climb] from={target_report['report_id']} to={ancestor['report_id']} reason=missing_col")
                                        target_report = ancestor
                                        missing_cols = []
                                        climb_resolved = True
                                        break
                                except (ValueError, OpSpecError):
                                    continue
                        if not climb_resolved:
                            prev_query = target_report.get("query", "")
                            if prev_query:
                                query = f"Based on '{prev_query}': {user_text}"
                            else:
                                query = data_query or user_text
                            active_report_query = query
                            active_report_kind = "derived"
                            active_report_parent_id = target_report.get("report_id")
                            active_report_derivation = "re-fetched for missing columns after lineage climb exhausted"
                            active_report_task = turn_scope.track(asyncio.create_task(call_report_api(query)))
                            continue

                    # D-14-02: Cache-first on low confidence — try in-memory ops before CacheExecutor
                    _resolve_conf = target_report.get("_resolve_confidence", 1.0)
                    if _resolve_conf < 0.7 and target_report.get("rows"):
                        try:
                            cache_first_result = execute_op(target_report["rows"], op_spec_result)
                            if cache_first_result:
                                print(f"  [memory.cache_first] op={op_spec_result.get('op_type')} rows={len(cache_first_result)} from={target_report['report_id']}")
                                await websocket.send(json.dumps({
                                    "type": "report_log",
                                    "query": user_text,
                                    "sql": target_report.get("sql", ""),
                                    "row_count": len(cache_first_result),
                                    "results": cache_first_result,
                                    "summary": op_spec_result.get("explanation", ""),
                                    "claude_interactions": [],
                                    "dashboard_b64": "",
                                    "report_id": target_report.get("report_id", ""),
                                    "kind": "derived",
                                    "source": "cache",
                                }))
                                session_memory.record(
                                    {"results": cache_first_result},
                                    kind="derived",
                                    parent_id=target_report.get("report_id"),
                                    origin_op=op_spec_result.get("op_type", "unknown"),
                                    topic=target_report.get("topic", ""),
                                    query=user_text,
                                    sql=target_report.get("sql", ""),
                                    derivation_summary=op_spec_result.get("explanation", ""),
                                )
                                # Voice the results
                                cf_messages = list(history) + [{
                                    "role": "user",
                                    "content": (
                                        f"[INTERNAL: You just ran a {op_spec_result.get('op_type')} operation on cached data "
                                        f"and got {len(cache_first_result)} result(s). Summarize briefly for the user. Stay in character.]"
                                    ),
                                }]
                                _ce = asyncio.Event()
                                cf_reply = await handle_llm_response(websocket, cf_messages, tts_client, _ce)
                                if cf_reply:
                                    history.append({"role": "assistant", "content": cf_reply})
                                continue
                        except (ValueError, OpSpecError):
                            # Missing column or incomplete op_spec — try lineage climb before refetch
                            chain = session_memory.lineage(target_report["report_id"])
                            climb_ok = False
                            for ancestor in chain[1:]:
                                try:
                                    climb_result = execute_op(ancestor["rows"], op_spec_result)
                                    if climb_result:
                                        print(f"  [memory.climb] from={target_report['report_id']} to={ancestor['report_id']} reason=narrow_set")
                                        await websocket.send(json.dumps({
                                            "type": "report_log",
                                            "query": user_text,
                                            "sql": ancestor.get("sql", ""),
                                            "row_count": len(climb_result),
                                            "results": climb_result,
                                            "summary": op_spec_result.get("explanation", ""),
                                            "claude_interactions": [],
                                            "dashboard_b64": "",
                                            "report_id": ancestor.get("report_id", ""),
                                            "kind": "derived",
                                            "source": "cache",
                                        }))
                                        session_memory.record(
                                            {"results": climb_result},
                                            kind="derived",
                                            parent_id=ancestor.get("report_id"),
                                            origin_op=op_spec_result.get("op_type", "unknown"),
                                            topic=ancestor.get("topic", ""),
                                            query=user_text,
                                            sql=ancestor.get("sql", ""),
                                            derivation_summary=op_spec_result.get("explanation", ""),
                                        )
                                        climb_ok = True
                                        break
                                except (ValueError, OpSpecError):
                                    continue
                            if climb_ok:
                                cf_messages = list(history) + [{
                                    "role": "user",
                                    "content": (
                                        f"[INTERNAL: You found the data by climbing to a parent report. "
                                        f"Summarize the results briefly. Stay in character.]"
                                    ),
                                }]
                                _ce = asyncio.Event()
                                cf_reply = await handle_llm_response(websocket, cf_messages, tts_client, _ce)
                                if cf_reply:
                                    history.append({"role": "assistant", "content": cf_reply})
                                continue
                            # Climb exhausted — fall through to CacheExecutor / refetch

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
                        print(f"  Executor error: {exec_err} -- falling back to fresh API query")
                        # Fall back: fire the user's question as a fresh data request
                        # rather than just apologizing. Keeps the user moving.
                        prev_query = target_report.get("query", "") if target_report else ""
                        fallback_query = (
                            f"Based on '{prev_query}': {user_text}" if prev_query else (data_query or user_text)
                        )
                        active_report_query = fallback_query
                        active_report_kind = "derived"
                        active_report_parent_id = target_report.get("report_id") if target_report else None
                        active_report_derivation = f"re-fetched after op error: {exec_err}"
                        active_report_task = turn_scope.track(asyncio.create_task(call_report_api(fallback_query)))
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
                        "report_id": target_report.get("report_id", ""),
                        "kind": "derived",
                        "source": "cache",
                    }))

                    # Cache the follow-up result as derived via SessionMemory (D-15)
                    # so subsequent follow-ups can reference it via demonstratives.
                    if result.get("rows"):
                        session_memory.record(
                            {"results": result["rows"]},
                            kind="derived",
                            parent_id=target_report.get("report_id"),
                            origin_op=op_spec_result.get("op_type", "unknown"),
                            topic=target_report.get("topic", ""),
                            query=user_text,
                            sql=target_report.get("sql", ""),
                            derivation_summary=op_spec_result.get("explanation", ""),
                        )

                    # D-03: Push to undo stack (base report id so undo can restore it)
                    if len(undo_stack) >= 5:
                        undo_stack.pop(0)
                    undo_stack.append({
                        "op_spec": op_spec_result,
                        "pre_op_report_id": target_report.get("report_id", ""),
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
                        active_report_kind = "derived"  # zero-result fallback: don't displace base report
                        active_report_parent_id = target_report.get("report_id")
                        active_report_derivation = "re-fetched after zero results"
                        active_report_task = turn_scope.track(asyncio.create_task(call_report_api(query)))
                        continue
                    else:
                        # Preview-first: send a small slice so Gemma can answer most questions
                        # without inflating context. Gemma signals [NEED_ALL_ROWS] when it
                        # needs the full list (e.g. "list every one by name").
                        _PREVIEW_N = 15
                        n_rows = result["row_count"]
                        preview_rows = result["rows"][:_PREVIEW_N]
                        preview_text = json.dumps(preview_rows, default=str)[:2000]
                        n_shown = len(preview_rows)
                        more_hint = (
                            f" ({n_shown} of {n_rows} shown — respond with [NEED_ALL_ROWS] if you need the full list to answer)"
                            if n_rows > _PREVIEW_N else ""
                        )
                        voice_messages = list(history[:-1]) + [{
                            "role": "user",
                            "content": (
                                f"{user_text}\n\n"
                                f"[op={op_spec_result.get('op_type', '')}: {op_spec_result.get('explanation', '')}. "
                                f"Result: EXACTLY {n_rows} row{'s' if n_rows != 1 else ''}{more_hint}\n"
                                f"<data>{preview_text}</data>\n\n"
                                "RULES (strict):\n"
                                "1. The <data> block is ground truth. Speak ONLY from it — never from memory, training knowledge, or prior turns.\n"
                                "2. Never invent numbers, names, or values. Never contradict what's shown.\n"
                                "3. If a field the user asked about is NOT in <data>, say you don't have that field — do not guess.\n"
                                "4. Scalar result (single row, single value — e.g. an aggregation): read that value directly.\n"
                                f"5. Count-style question: the answer is EXACTLY {n_rows}.\n"
                                "6. Multiple rows: list each row's value individually. Do NOT average or summarize unless the user explicitly said 'average', 'mean', or 'total'.\n"
                                "7. Single-item answer: name it directly.\n"
                                "8. Need the full list but not all rows are shown → output [NEED_ALL_ROWS] and stop.\n"
                                "9. Keep it to 1-2 natural sentences.]"
                            ),
                        }]

                    _ce = asyncio.Event()
                    spoken = await handle_llm_response_text_only(websocket, voice_messages, _ce)

                    # If Gemma needs the full row list, re-call with all rows from the report
                    if "[NEED_ALL_ROWS]" in (spoken or ""):
                        all_rows_text = json.dumps(result["rows"], default=str)[:12000]
                        full_messages = list(history[:-1]) + [{
                            "role": "user",
                            "content": (
                                f"{user_text}\n\n"
                                f"[Here are all {n_rows} rows as requested:\n"
                                f"<data>{all_rows_text}</data>\n\n"
                                f"List every item. There are EXACTLY {n_rows} — do not add or omit any. "
                                "Present naturally.]"
                            ),
                        }]
                        _ce = asyncio.Event()
                        spoken = await handle_llm_response_text_only(websocket, full_messages, _ce)

                    if not spoken or not is_quality_response(spoken):
                        spoken = op_spec_result.get("explanation", "Done.")
                    history.append({"role": "assistant", "content": spoken})
                    await websocket.send(json.dumps({"type": "sentence", "text": spoken}))
                    _ce2 = asyncio.Event()
                    await tts_full_response(websocket, spoken, tts_client, _ce2)
                    await websocket.send(json.dumps({"type": "done"}))
                    continue

                elif intent == "follow_up_on_previous" and not session_cache.all_reports():
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
                    active_report_task = turn_scope.track(asyncio.create_task(call_report_api(query)))
                    continue

                elif intent == "list_cached_data":
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
                        # D-20-06: Dynamic fallback — use cached reports or conversational prompt
                        cached = session_cache.all_reports()
                        if cached:
                            cached_queries = [r["query"] for r in cached]
                            topics_text = f"You've already pulled: {', '.join(cached_queries)}"
                        else:
                            topics_text = "No data pulled yet this session"

                    discovery_messages = list(history) + [{
                        "role": "user",
                        "content": (
                            f"[INTERNAL: The user wants to know what data topics are available. "
                            f"{topics_text}. "
                            "If data has been pulled, list those topics naturally. "
                            "If no data yet, let them know you can help explore any data they have access to "
                            "and ask what kind of information they're looking for. "
                            "Keep it brief and conversational.]"
                        ),
                    }]
                    _ce = asyncio.Event()
                    reply = await handle_llm_response(websocket, discovery_messages, tts_client, _ce)
                    if reply:
                        history.append({"role": "assistant", "content": reply})
                    continue

                elif intent == "compare_reports":
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
                            active_report_task = turn_scope.track(asyncio.create_task(call_report_api(query)))
                            # D-20-02: opening_phrase already flushed to TTS above
                            if opening_phrase:
                                history.append({"role": "assistant", "content": opening_phrase})
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

                    # Cache comparison output as derived so user can reference it via classifier
                    session_cache.store({"results": result["rows"]}, query=user_text, sql="", kind="derived")

                    # Voice results
                    preview_rows = result["rows"][:5]
                    preview_text = json.dumps(preview_rows, default=str)[:500]
                    voice_messages = list(history) + [{
                        "role": "user",
                        "content": (
                            f"[INTERNAL: Comparison done. Merged {topic_a} and {topic_b} on '{compare_col}'. "
                            f"Result: {result['row_count']} rows. Preview: <data>{preview_text}</data>\n\n"
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

                # confirm and cancel intents fall through to normal_chat
                # normal_chat falls through to the existing generation phase below

                # --- Phase B: Concurrent generation + stop listener ---
                cancel_event = asyncio.Event()

                # If speculative chat buffer is ready, use it — avoids a second LLM call.
                # Otherwise fall back to a fresh handle_llm_response call.
                if speculative_chat_task is not None:
                    # Speculative buffer was running in parallel with intent classification.
                    # Await it (may already be done), then send result directly to UI/TTS.
                    buffered_reply = await speculative_chat_task
                    speculative_chat_task = None

                    async def _send_buffered(reply: str, ws, tts, ce: asyncio.Event) -> str:
                        if not reply:
                            return ""
                        t0 = time.perf_counter()
                        await ws.send(json.dumps({"type": "sentence", "text": reply}))
                        await tts_full_response(ws, reply, tts, ce)
                        if ce.is_set():
                            await ws.send(json.dumps({"type": "interrupted"}))
                        else:
                            await ws.send(json.dumps({"type": "done"}))
                        print(f"  Speculative chat delivered in {(time.perf_counter()-t0)*1000:.0f}ms")
                        return reply

                    gen_task = asyncio.create_task(
                        _send_buffered(buffered_reply, websocket, tts_client, cancel_event)
                    )
                else:
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
                            turn_scope.cancel()  # D-19: cancel turn scope too
                            return
                        elif parsed.get("type") == "speech_start":
                            cancel_event.set()  # Interrupt immediately on speech
                            turn_scope.cancel()  # D-19
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
                    await deliver_report_result(websocket, active_report_task, history, tts_client, active_report_query, session_cache=session_cache, cache_kind=active_report_kind, session_memory=session_memory, parent_report_id=active_report_parent_id, origin_op="fetch", derivation_summary=active_report_derivation)
                    if last_intent_result:
                        await _apply_op_chain(websocket, last_intent_result, session_cache, active_report_query)
                        last_intent_result = None
                    active_report_kind = "base"
                    active_report_task = None
                    active_report_query = ""
                    active_report_parent_id = None
                    active_report_derivation = ""
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
