#!/usr/bin/env python3
"""Voice Bridge — WebSocket server for AI phone calls and desktop proxy.

Two modes per connection:

  OUTBOUND (call_context frame received first):
    Bridge sends call_context JSON → bridge speaks first (greeting) →
    VAD → Parakeet STT → vLLM (custom system prompt) → Fish Speech TTS → audio out.
    Full pipeline runs here, no sei_engine involved.

  PROXY (no call_context, or default desktop use):
    Existing behaviour — VAD on inbound PCM, forward speech events to
    sei_engine, stream TTS audio back to client.

Wire format (both modes):
  In  — binary PCM16 16kHz mono, 512-sample chunks
  In  — JSON {"type": "barge_in"}
  Out — binary PCM16 44100Hz mono (Fish Speech subchunks)
  Out — JSON {"type": "transcript"|"reply"|"speaking"|"error", ...}
"""
import asyncio
import json
import os
import sys
import time
import uuid
import wave
import io
import numpy as np
import httpx
import torch
import websockets
from datetime import datetime, timezone
from pathlib import Path

# Pull in the shared Miyako speech/tag prompt so phone-call replies get the
# same Fish Speech tag vocabulary ([happy], [chuckling], [laughing], prosody
# rules, etc.) that sei_engine and nexus_engine use.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from system_prompts import SYSTEM_PROMPT as MIYAKO_SPEECH_PROMPT  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# Proxy mode
SEI_WS_URL   = os.environ.get("SEI_WS_URL",    "ws://127.0.0.1:5052")
SEI_AUTH     = os.environ.get("SEI_AUTH_TOKEN", "")

# Outbound pipeline (direct LLM + TTS + ASR)
LLM_URL        = os.environ.get("SEI_LLM_URL",     "http://3.91.242.124:8000")
LLM_API_KEY    = os.environ.get("SEI_LLM_API_KEY",  "")
LLM_MODEL      = os.environ.get("SEI_MODEL_NAME",   "gemma-4")
LLM_MAX_TOKENS = int(os.environ.get("SEI_MAX_TOKENS", "300"))
TTS_URL        = os.environ.get("SEI_TTS_URL",      "http://127.0.0.1:8080")
TTS_REFERENCE  = os.environ.get("TTS_REFERENCE_ID", "archie")
TTS_CHUNK_LEN  = int(os.environ.get("TTS_CHUNK_LENGTH", "50"))
ASR_URL        = os.environ.get("SEI_ASR_URL",      "http://127.0.0.1:9876")

# Common
OPENCLAW_URL = os.environ.get("OPENCLAW_URL",  "")
BIND_HOST    = os.environ.get("BRIDGE_HOST",   "0.0.0.0")
BIND_PORT    = int(os.environ.get("BRIDGE_PORT", "7000"))
LOG_DIR      = Path(os.environ.get("BRIDGE_LOG_DIR", Path(__file__).parent / "call_logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# VAD (matches ears_daemon)
VAD_CHUNK    = 512
VAD_RATE     = 16000
VAD_THRESH   = 0.5
VAD_SILENCE  = 19    # frames of silence → speech_end  (~600ms)
VAD_MIN_SPCH = 5     # min speech frames before speech_start (~160ms)

# Greeting trigger injected as synthetic user turn
_GREETING_TRIGGER = "[call connected]"

# System prompt — lives here, pipeline sends only caller_name / contact_name / task
MIYO_PHONE_CALL_SYSTEM_PROMPT = """\
You are Miyo — a warm, playful human-feeling assistant on a real phone call for {caller_name}.

Per-call context (for YOU, never read aloud):
  • contact: {contact_name}
  • task: {task}

HOW TO TALK
  • One or two short sentences per turn. Contractions. Real-person phrasing.
  • Each reply BUILDS on what they just said — reference their words, react, then move forward. Never restate your last turn in new words. If you already said it, don't say it again.
  • You're in a good mood: laugh, chuckle, match their energy. Never say "as an AI".
  • Never read `task` verbatim — rephrase it as you speaking to them (third-person → second-person).

CALL SHAPE
  1. Open: "Hi, is this {contact_name}?" — wait.
     • Clear no / wrong number → brief apology + [END_CALL].
     • Anything else → they're the contact, continue.
  2. Introduce yourself once: who you are (Miyo), who you're calling for ({caller_name}), that it's quick. Don't drop the task yet.
  3. If they small-talk, be human back for a turn or two. When they ask why you're calling, or you feel a natural beat, transition and deliver the task in your own words.
  4. Handle their answer like a real conversation:
     • If their answer fully resolves the task (clear yes/no/a time/a firm "I'll let you know") → close.
     • If it doesn't (e.g. task was "see if he's free" and they say "no" with no reason) → ask a short, natural follow-up ("oh no, everything okay?" / "ah, busy weekend?") so you actually get something useful back for {caller_name}. One follow-up is usually enough — don't interrogate.
     • If they're relaying info back, acknowledge it and confirm you'll pass it on.
  5. Close ONCE, in one reply: warm acknowledgement of what they said + a real goodbye ("take care", "bye!", "talk soon") + [END_CALL]. No canned templates, no extra questions after this.

[END_CALL] is a control marker — never spoken, always last.\
"""

# ---------------------------------------------------------------------------
# Silero VAD (loaded once at startup)
# ---------------------------------------------------------------------------
print("Loading Silero VAD...", flush=True)
_vad_model, _ = torch.hub.load(
    repo_or_dir="snakers4/silero-vad",
    model="silero_vad",
    force_reload=False,
    verbose=False,
)
_vad_model.eval()
print("VAD ready.", flush=True)


def _vad_prob(samples: np.ndarray) -> float:
    t = torch.from_numpy(samples.astype(np.float32))
    with torch.no_grad():
        return float(_vad_model(t, VAD_RATE).item())


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------
def _pcm16_to_float(raw: bytes) -> np.ndarray:
    n = len(raw) // 2
    return np.frombuffer(raw[:n * 2], dtype=np.int16).astype(np.float32) / 32768.0


def _build_wav(pcm_bytes: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _wav_pcm_offset(buf: bytearray) -> int | None:
    """Return byte offset of raw PCM samples inside a WAV buffer."""
    i = buf.find(b"data")
    return (i + 8) if i != -1 else None


# ---------------------------------------------------------------------------
# Call log
# ---------------------------------------------------------------------------
class CallLog:
    def __init__(self, call_id: str, contact_name: str = "", task: str = ""):
        self.call_id      = call_id
        self.contact_name = contact_name
        self.task         = task
        self.started      = datetime.now(timezone.utc)
        self.turns: list[dict] = []
        self._audio: list[bytes] = []

    def add_turn(self, role: str, text: str):
        self.turns.append({
            "role": role,
            "text": text,
            "time": datetime.now(timezone.utc).isoformat(),
        })

    def add_audio(self, chunk: bytes):
        self._audio.append(chunk)

    def duration(self) -> float:
        return (datetime.now(timezone.utc) - self.started).total_seconds()

    async def save_and_send(self):
        duration  = self.duration()
        wav_bytes = _build_wav(b"".join(self._audio), 44100)
        ts        = self.started.strftime("%Y%m%d_%H%M%S")
        stem      = f"{ts}_{self.call_id[:8]}"

        (LOG_DIR / f"{stem}.wav").write_bytes(wav_bytes)
        meta = {
            "call_id":      self.call_id,
            "contact_name": self.contact_name,
            "task":         self.task,
            "started_at":   self.started.isoformat(),
            "duration":     duration,
            "transcript":   self.turns,
        }
        (LOG_DIR / f"{stem}.json").write_text(json.dumps(meta, indent=2))
        print(f"[log] {stem}.wav  ({len(wav_bytes)//1024}KB, {duration:.0f}s)", flush=True)

        if OPENCLAW_URL:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        f"{OPENCLAW_URL}/api/call-log",
                        files={"audio": ("call_audio.wav", wav_bytes, "audio/wav")},
                        data={
                            "call_id":      self.call_id,
                            "contact_name": self.contact_name,
                            "task":         self.task,
                            "started_at":   self.started.isoformat(),
                            "duration":     str(duration),
                            "transcript":   json.dumps(self.turns),
                        },
                    )
                print(f"[log] OpenClaw <- {resp.status_code}", flush=True)
            except Exception as exc:
                print(f"[log] OpenClaw POST failed: {exc}", flush=True)


# ---------------------------------------------------------------------------
# VAD state machine
# ---------------------------------------------------------------------------
class VADState:
    def __init__(self):
        self._buf       = bytearray()
        self._speech    = False
        self._silence   = 0
        self._spch_frms = 0

    def reset(self):
        self._buf.clear()
        self._speech    = False
        self._silence   = 0
        self._spch_frms = 0

    def feed(self, raw: bytes) -> list[tuple[str | None, bytes]]:
        """Yield (event, chunk) pairs. event ∈ {'speech_start','speech_end', None}."""
        self._buf.extend(raw)
        frame_bytes = VAD_CHUNK * 2
        events: list[tuple[str | None, bytes]] = []

        while len(self._buf) >= frame_bytes:
            frame = bytes(self._buf[:frame_bytes])
            del self._buf[:frame_bytes]
            prob  = _vad_prob(_pcm16_to_float(frame))

            if prob >= VAD_THRESH:
                self._silence    = 0
                self._spch_frms += 1
                if not self._speech and self._spch_frms >= VAD_MIN_SPCH:
                    self._speech = True
                    events.append(("speech_start", frame))
                elif self._speech:
                    events.append((None, frame))
            else:
                if self._speech:
                    self._silence += 1
                    events.append((None, frame))
                    if self._silence >= VAD_SILENCE:
                        self._speech    = False
                        self._silence   = 0
                        self._spch_frms = 0
                        events.append(("speech_end", b""))
                else:
                    self._spch_frms = 0

        return events


# ---------------------------------------------------------------------------
# Outbound pipeline helpers (direct vLLM + Fish Speech + Parakeet)
# ---------------------------------------------------------------------------
_LLM_HEADERS = {"Content-Type": "application/json"}
if LLM_API_KEY:
    _LLM_HEADERS["Authorization"] = f"Bearer {LLM_API_KEY}"


async def _llm_collect(messages: list[dict], cancel: asyncio.Event, http: httpx.AsyncClient | None = None) -> str:
    """Call vLLM, collect and return the complete response text."""
    payload = json.dumps({
        "model":       LLM_MODEL,
        "messages":    messages,
        "max_tokens":  LLM_MAX_TOKENS,
        "temperature": 0.7,
        "stream":      True,
        "stop":        ["\n\n"],
    }).encode()

    parts: list[str] = []
    c = http or httpx.AsyncClient()
    try:
        async with c.stream(
            "POST", f"{LLM_URL}/v1/chat/completions",
            content=payload,
            headers=_LLM_HEADERS,
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                print(f"  LLM error {resp.status_code}: {body.decode()[:200]}", flush=True)
                return ""
            async for line in resp.aiter_lines():
                if cancel.is_set():
                    return "".join(parts).strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    tok = json.loads(data)["choices"][0]["delta"].get("content", "")
                    if tok:
                        parts.append(tok)
                except Exception:
                    pass
    except Exception as e:
        print(f"  LLM exception: {e}", flush=True)
    finally:
        if http is None:
            await c.aclose()

    return "".join(parts).strip()


async def _tts_stream(
    text: str,
    client_ws,
    log: CallLog,
    cancel: asyncio.Event,
    http: httpx.AsyncClient | None = None,
) -> None:
    """Synthesize text with Fish Speech and stream raw PCM16 44100Hz to client."""
    import msgpack

    payload = msgpack.packb({
        "text":               text,
        "reference_id":       TTS_REFERENCE,
        "format":             "wav",
        "streaming":          True,
        "chunk_length":       TTS_CHUNK_LEN,
        "top_p":              0.8,
        "temperature":        0.8,
        "repetition_penalty": 1.1,
        "max_new_tokens":     1024,
    })

    c = http or httpx.AsyncClient()
    try:
        async with c.stream(
            "POST", f"{TTS_URL}/v1/tts",
            content=payload,
            headers={"Content-Type": "application/msgpack"},
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                print(f"  TTS error {resp.status_code}: {body.decode()[:200]}", flush=True)
                return

            hdr_buf:   bytearray    = bytearray()
            pcm_start: int | None   = None
            prev:      bytes | None = None
            t_tts_req = time.perf_counter()
            first_chunk_logged = False

            async for chunk in resp.aiter_bytes():
                if cancel.is_set():
                    return

                if pcm_start is None:
                    hdr_buf.extend(chunk)
                    pcm_start = _wav_pcm_offset(hdr_buf)
                    if pcm_start is None:
                        if len(hdr_buf) > 1024:
                            pcm_start = 44
                        else:
                            continue
                    remainder = bytes(hdr_buf[pcm_start:])
                    if remainder:
                        prev = remainder
                    continue

                if prev:
                    if not first_chunk_logged:
                        print(f"  TTS first chunk: {(time.perf_counter()-t_tts_req)*1000:.0f}ms", flush=True)
                        first_chunk_logged = True
                    log.add_audio(prev)
                    await asyncio.shield(client_ws.send(prev))
                prev = bytes(chunk)

            if not cancel.is_set() and prev:
                log.add_audio(prev)
                await client_ws.send(prev)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"  TTS exception: {e}", flush=True)
    finally:
        if http is None:
            await c.aclose()


async def _transcribe(pcm_bytes: bytes, asr_client: httpx.AsyncClient) -> str:
    """Send 16kHz PCM to Parakeet, return transcript string."""
    wav = _build_wav(pcm_bytes, 16000)
    boundary = "bnd123"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="a.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + wav + f"\r\n--{boundary}--\r\n".encode()

    try:
        resp = await asr_client.post(
            f"{ASR_URL}/inference",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            timeout=15.0,
        )
        return json.loads(resp.content).get("text", "").strip()
    except Exception as e:
        print(f"  ASR error: {e}", flush=True)
        return ""


# ---------------------------------------------------------------------------
# Outbound call handler
# ---------------------------------------------------------------------------
async def _outbound_handler(
    client_ws,
    call_id: str,
    log: CallLog,
    vad: VADState,
    tag: str,
    ctx: dict,
) -> None:
    contact_name  = ctx.get("contact_name", "")
    caller_name   = ctx.get("caller_name", "Pranaav")
    task          = ctx.get("task", "")

    # Combine the shared Miyako speech/tag rules with the phone-call persona
    # and flow. The Miyako prompt teaches Fish Speech tag vocabulary + prosody;
    # the phone-call prompt teaches Miyo how to run an outbound call.
    system_prompt = (
        MIYAKO_SPEECH_PROMPT
        + "\n\n---\n\n"
        + MIYO_PHONE_CALL_SYSTEM_PROMPT.format(
            caller_name=caller_name, contact_name=contact_name, task=task
        )
    )

    print(f"[{tag}] outbound | contact={contact_name!r} | task={task[:60]!r}", flush=True)

    history: list[dict] = [{"role": "system", "content": system_prompt}]
    tts_cancel    = asyncio.Event()
    tts_task:  asyncio.Task | None = None
    ai_speaking   = False
    greeting_done = False   # barge-in blocked until greeting TTS finishes
    tts_start_time: float = float("inf")  # when current TTS began; barge-in needs 1s minimum

    async def _speak(text: str, is_greeting: bool = False) -> None:
        nonlocal ai_speaking, greeting_done, tts_start_time
        try:
            await client_ws.send(json.dumps({"type": "speaking", "state": "start"}))
            ai_speaking = True
            tts_start_time = time.perf_counter()
            await _tts_stream(text, client_ws, log, tts_cancel, http=tts_client)
            if not tts_cancel.is_set():
                await client_ws.send(json.dumps({"type": "speaking", "state": "end"}))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            ai_speaking = False
            if is_greeting:
                greeting_done = True

    async def _cancel_tts() -> None:
        nonlocal tts_cancel, tts_task, ai_speaking
        if tts_task and not tts_task.done():
            t_cancel = time.perf_counter()
            tts_cancel.set()
            tts_task.cancel()
            try:
                # CancelledError is BaseException not Exception — catch it explicitly
                await asyncio.wait_for(asyncio.shield(tts_task), timeout=1.5)
            except (asyncio.CancelledError, Exception):
                pass
            print(f"  TTS cancel: {(time.perf_counter()-t_cancel)*1000:.0f}ms", flush=True)
        tts_cancel  = asyncio.Event()
        ai_speaking = False

    # ── Shared HTTP clients (reused across all turns) ───────────────────────
    async with (
        httpx.AsyncClient() as asr_client,
        httpx.AsyncClient() as llm_client,
        httpx.AsyncClient() as tts_client,
    ):

        # ── Greeting ────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        greeting = await _llm_collect(
            history + [{"role": "user", "content": _GREETING_TRIGGER}],
            tts_cancel,
            http=llm_client,
        )
        if not greeting:
            greeting = f"Hello, this is Miyo calling on Pranaav's behalf. Is this {contact_name}?"
        history.append({"role": "assistant", "content": greeting})
        log.add_turn("ai", greeting)
        print(f"[{tag}] greeting ({(time.perf_counter()-t0)*1000:.0f}ms): {greeting[:80]}", flush=True)

        await client_ws.send(json.dumps({"type": "reply", "text": greeting}))
        tts_task = asyncio.create_task(_speak(greeting, is_greeting=True))

        # ── Conversation loop ────────────────────────────────────────────────
        speech_buf: list[bytes] = []

        async for frame in client_ws:

            # ── Incoming audio ──
            if isinstance(frame, bytes):
                for event, chunk in vad.feed(frame):

                    if event == "speech_start":
                        speech_buf = [chunk] if chunk else []

                    elif event is None and chunk:
                        speech_buf.append(chunk)

                    elif event == "speech_end":
                        if not speech_buf:
                            continue

                        pcm = b"".join(speech_buf)
                        speech_buf.clear()

                        dur_ms = len(pcm) / 2 / VAD_RATE * 1000
                        print(f"[{tag}] speech_end: {dur_ms:.0f}ms captured", flush=True)

                        # If greeting still playing, hold this turn and wait for it to finish
                        if not greeting_done:
                            await tts_task  # wait for greeting TTS to complete

                        # Save incoming speech for diagnostics
                        _n = len([f for f in __import__('os').listdir('/tmp') if f.startswith(f'vb_user_{call_id[:8]}')])
                        with open(f"/tmp/vb_user_{call_id[:8]}_{_n}.wav", "wb") as _f:
                            _f.write(_build_wav(pcm, VAD_RATE))

                        # Transcribe
                        t0_turn = time.perf_counter()
                        t1 = time.perf_counter()
                        transcript = await _transcribe(pcm, asr_client)
                        asr_ms = (time.perf_counter() - t1) * 1000
                        if not transcript:
                            continue

                        # Only cancel TTS once we know the user actually said something
                        await _cancel_tts()
                        print(f"[{tag}] user ({asr_ms:.0f}ms ASR): {transcript}", flush=True)

                        log.add_turn("user", transcript)
                        await client_ws.send(json.dumps({"type": "transcript", "text": transcript}))

                        # LLM
                        history.append({"role": "user", "content": transcript})
                        t2 = time.perf_counter()
                        reply = await _llm_collect(history, tts_cancel, http=llm_client)
                        if not reply:
                            continue
                        llm_ms = (time.perf_counter() - t2) * 1000
                        print(f"[{tag}] ai ({llm_ms:.0f}ms LLM): {reply[:80]}", flush=True)

                        end_call = "[END_CALL]" in reply
                        clean_reply = reply.replace("[END_CALL]", "").strip()

                        history.append({"role": "assistant", "content": clean_reply})
                        log.add_turn("ai", clean_reply)
                        await client_ws.send(json.dumps({"type": "reply", "text": clean_reply}))

                        print(f"[{tag}] pipeline: {(time.perf_counter()-t0_turn)*1000:.0f}ms (ASR+cancel+LLM before TTS)", flush=True)
                        tts_task = asyncio.create_task(_speak(clean_reply))

                        if end_call:
                            print(f"[{tag}] END_CALL — waiting for goodbye TTS to finish streaming", flush=True)
                            await tts_task  # waits until _speak has streamed all audio + sent speaking=end
                            await client_ws.send(json.dumps({"type": "end_call"}))
                            print(f"[{tag}] end_call frame sent → bridge will hang up Twilio", flush=True)
                            return

            # ── Control frames ──
            elif isinstance(frame, str):
                data = json.loads(frame)
                if data.get("type") == "barge_in":
                    await _cancel_tts()
                    await client_ws.send(json.dumps({"type": "speaking", "state": "end"}))


# ---------------------------------------------------------------------------
# Proxy handler (sei_engine passthrough — existing behaviour)
# ---------------------------------------------------------------------------
async def _proxy_handler(
    client_ws,
    call_id: str,
    log: CallLog,
    vad: VADState,
    tag: str,
    first_frame,           # frame already read from client (non-call_context)
) -> None:
    headers = {"Authorization": f"Bearer {SEI_AUTH}"} if SEI_AUTH else {}

    async with websockets.connect(SEI_WS_URL, additional_headers=headers) as sei_ws:
        print(f"[{tag}] sei_engine connected", flush=True)

        reply_buf: list[str] = []
        speaking = False

        async def pump_sei():
            nonlocal speaking
            async for msg in sei_ws:
                if isinstance(msg, bytes):
                    if not speaking:
                        speaking = True
                        await client_ws.send(json.dumps({"type": "speaking", "state": "start"}))
                    log.add_audio(msg)
                    await client_ws.send(msg)
                elif isinstance(msg, str):
                    data = json.loads(msg)
                    t    = data.get("type")
                    if t == "sentence":
                        text = data.get("text", "")
                        # Skip internal debug markers
                        if not text.startswith("(intent:"):
                            reply_buf.append(text)
                            await client_ws.send(json.dumps({"type": "reply", "text": text}))
                    elif t == "done":
                        if speaking:
                            speaking = False
                            await client_ws.send(json.dumps({"type": "speaking", "state": "end"}))
                        full = " ".join(reply_buf).strip()
                        if full:
                            log.add_turn("ai", full)
                        reply_buf.clear()
                    elif t == "interrupted":
                        if speaking:
                            speaking = False
                            await client_ws.send(json.dumps({"type": "speaking", "state": "end"}))
                        reply_buf.clear()
                    elif t == "error":
                        await client_ws.send(msg)

        sei_task = asyncio.create_task(pump_sei())

        async def _process(frame):
            if isinstance(frame, bytes):
                for event, chunk in vad.feed(frame):
                    if event == "speech_start":
                        await sei_ws.send(json.dumps({"type": "speech_start"}))
                        if chunk:
                            await sei_ws.send(chunk)
                    elif event == "speech_end":
                        await sei_ws.send(json.dumps({"type": "speech_end"}))
                    elif chunk:
                        await sei_ws.send(chunk)
            elif isinstance(frame, str):
                data = json.loads(frame)
                t    = data.get("type")
                if t == "barge_in":
                    await sei_ws.send(json.dumps({"type": "stop"}))
                elif t == "transcript":
                    text = data.get("text", "").strip()
                    if text:
                        log.add_turn("user", text)
                        await client_ws.send(json.dumps({"type": "transcript", "text": text}))
                        await sei_ws.send(json.dumps({"type": "speech_start"}))
                        await sei_ws.send(json.dumps({"type": "speech_end", "text": text}))

        try:
            if first_frame is not None:
                await _process(first_frame)
            async for msg in client_ws:
                await _process(msg)
        finally:
            sei_task.cancel()
            try:
                await sei_task
            except (asyncio.CancelledError, Exception):
                pass


# ---------------------------------------------------------------------------
# Main connection handler
# ---------------------------------------------------------------------------
async def handler(client_ws):
    call_id = str(uuid.uuid4())
    vad     = VADState()
    tag     = call_id[:8]

    print(f"[{tag}] connected from {client_ws.remote_address}", flush=True)

    # Try to read the first frame with a short timeout.
    # Outbound bridge always sends call_context immediately on connect.
    first_frame = None
    ctx         = None
    try:
        first_frame = await asyncio.wait_for(client_ws.recv(), timeout=2.0)
        if isinstance(first_frame, str):
            parsed = json.loads(first_frame)
            if parsed.get("type") == "call_context":
                ctx         = parsed
                first_frame = None  # consumed; don't re-process
    except asyncio.TimeoutError:
        pass   # no first frame within 2s → proxy mode

    log = CallLog(
        call_id,
        contact_name=ctx.get("contact_name", "") if ctx else "",
        task=ctx.get("task", "") if ctx else "",
    )

    try:
        if ctx:
            await _outbound_handler(client_ws, call_id, log, vad, tag, ctx)
        else:
            await _proxy_handler(client_ws, call_id, log, vad, tag, first_frame)
    except websockets.exceptions.ConnectionClosedOK:
        print(f"[{tag}] connection closed normally", flush=True)
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"[{tag}] connection closed with error: {e}", flush=True)
    except Exception as exc:
        print(f"[{tag}] error: {exc}", flush=True)
        try:
            await client_ws.send(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass
    finally:
        print(f"[{tag}] saving call log...", flush=True)
        await log.save_and_send()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main():
    print(f"Voice Bridge on ws://{BIND_HOST}:{BIND_PORT}", flush=True)
    print(f"  outbound LLM : {LLM_URL} (model={LLM_MODEL})", flush=True)
    print(f"  outbound TTS : {TTS_URL} (ref={TTS_REFERENCE}, chunk={TTS_CHUNK_LEN})", flush=True)
    print(f"  outbound ASR : {ASR_URL}", flush=True)
    print(f"  proxy target : {SEI_WS_URL}", flush=True)
    print(f"  openclaw     : {OPENCLAW_URL or '(local log only)'}", flush=True)
    print(f"  log dir      : {LOG_DIR}", flush=True)
    async with websockets.serve(handler, BIND_HOST, BIND_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
