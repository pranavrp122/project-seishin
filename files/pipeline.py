"""
Project Seishin — Phase 1: Voice-to-Voice Pipeline
Parakeet STT → Qwen 3.5 → Fish Audio TTS
Target: <150ms time-to-first-audio
"""

import asyncio
import json
import time
import logging
import os
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional
import numpy as np

import sounddevice as sd
import soundfile as sf
import websockets
import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("seishin.pipeline")


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

@dataclass
class SeishinConfig:
    # STT — Parakeet via NVIDIA NIM
    nim_api_key: str = os.getenv("NIM_API_KEY", "")
    nim_stt_url: str = "https://integrate.api.nvidia.com/v1/audio/transcriptions"
    nim_stt_model: str = "nvidia/parakeet-tdt-1.1b"

    # LLM — Qwen via vLLM local server
    vllm_base_url: str = os.getenv("VLLM_URL", "http://localhost:8000/v1")
    vllm_model: str = "Qwen/Qwen2.5-35B-Instruct-GPTQ-Int4"

    # TTS — Fish Audio local server
    fish_audio_url: str = os.getenv("FISH_AUDIO_URL", "http://localhost:8080")
    fish_reference_id: str = os.getenv("FISH_REFERENCE_ID", "")  # voice character ID

    # Audio
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration_ms: int = 30
    vad_silence_threshold_ms: int = 700   # ms of silence to end utterance
    vad_energy_threshold: float = 0.01

    # Pipeline
    system_prompt: str = (
        "You are Seishin, an emotionally intelligent AI companion. "
        "Respond naturally, conversationally, and concisely — as if speaking aloud. "
        "No markdown, no lists, no headers. Just natural speech. "
        "Be warm, present, and emotionally aware."
    )
    max_response_tokens: int = 256
    ws_port: int = 8765  # dashboard WebSocket


# ─────────────────────────────────────────────
# Latency tracker
# ─────────────────────────────────────────────

@dataclass
class LatencyTrace:
    start: float = field(default_factory=time.perf_counter)
    stt_done: Optional[float] = None
    llm_first_token: Optional[float] = None
    tts_first_audio: Optional[float] = None

    def mark_stt(self):
        self.stt_done = time.perf_counter()

    def mark_llm(self):
        self.llm_first_token = time.perf_counter()

    def mark_tts(self):
        self.tts_first_audio = time.perf_counter()

    def report(self) -> dict:
        now = time.perf_counter()
        return {
            "stt_ms": round((self.stt_done - self.start) * 1000, 1) if self.stt_done else None,
            "llm_ms": round((self.llm_first_token - self.stt_done) * 1000, 1) if self.llm_first_token and self.stt_done else None,
            "tts_ms": round((self.tts_first_audio - self.llm_first_token) * 1000, 1) if self.tts_first_audio and self.llm_first_token else None,
            "total_ms": round((self.tts_first_audio - self.start) * 1000, 1) if self.tts_first_audio else round((now - self.start) * 1000, 1),
        }


# ─────────────────────────────────────────────
# VAD — Simple energy-based voice activity detector
# ─────────────────────────────────────────────

class SimpleVAD:
    """
    Energy-based VAD. For production, swap with Silero VAD:
        pip install silero-vad
    """
    def __init__(self, cfg: SeishinConfig):
        self.threshold = cfg.vad_energy_threshold
        self.silence_frames = 0
        self.silence_limit = int(cfg.vad_silence_threshold_ms / cfg.chunk_duration_ms)
        self.triggered = False

    def is_speech(self, chunk: np.ndarray) -> bool:
        energy = float(np.sqrt(np.mean(chunk ** 2)))
        return energy > self.threshold

    def process(self, chunk: np.ndarray) -> str:
        """Returns: 'speech' | 'silence' | 'end_of_utterance'"""
        if self.is_speech(chunk):
            self.silence_frames = 0
            self.triggered = True
            return "speech"
        else:
            if self.triggered:
                self.silence_frames += 1
                if self.silence_frames >= self.silence_limit:
                    self.triggered = False
                    self.silence_frames = 0
                    return "end_of_utterance"
            return "silence"


# ─────────────────────────────────────────────
# STT — Parakeet TDT 1.1B via NVIDIA NIM
# ─────────────────────────────────────────────

class ParakeetSTT:
    def __init__(self, cfg: SeishinConfig):
        self.cfg = cfg

    async def transcribe(self, audio_bytes: bytes, session: aiohttp.ClientSession) -> str:
        """Send audio bytes to NVIDIA NIM Parakeet endpoint."""
        headers = {"Authorization": f"Bearer {self.cfg.nim_api_key}"}
        form = aiohttp.FormData()
        form.add_field("file", audio_bytes, filename="audio.wav", content_type="audio/wav")
        form.add_field("model", self.cfg.nim_stt_model)
        form.add_field("response_format", "json")

        async with session.post(self.cfg.nim_stt_url, headers=headers, data=form) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"STT error {resp.status}: {body}")
            result = await resp.json()
            return result.get("text", "").strip()


# ─────────────────────────────────────────────
# LLM — Qwen 3.5 via vLLM (streaming)
# ─────────────────────────────────────────────

class QwenLLM:
    def __init__(self, cfg: SeishinConfig):
        self.cfg = cfg
        self.history: list[dict] = []

    async def stream(
        self, user_text: str, session: aiohttp.ClientSession
    ) -> AsyncGenerator[str, None]:
        """Yields text tokens as they stream from vLLM."""
        self.history.append({"role": "user", "content": user_text})

        payload = {
            "model": self.cfg.vllm_model,
            "messages": [
                {"role": "system", "content": self.cfg.system_prompt},
                *self.history,
            ],
            "max_tokens": self.cfg.max_response_tokens,
            "stream": True,
            "temperature": 0.75,
            "top_p": 0.9,
        }

        full_response = []
        url = f"{self.cfg.vllm_base_url}/chat/completions"

        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"LLM error {resp.status}: {body}")

            async for raw_line in resp.content:
                line = raw_line.decode("utf-8").strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        full_response.append(delta)
                        yield delta
                except (json.JSONDecodeError, KeyError):
                    continue

        assistant_text = "".join(full_response)
        self.history.append({"role": "assistant", "content": assistant_text})

    def clear_history(self):
        self.history = []


# ─────────────────────────────────────────────
# Sentence chunker — feeds TTS sentence-by-sentence for low latency
# ─────────────────────────────────────────────

class SentenceChunker:
    """
    Buffers streamed LLM tokens and yields complete sentences.
    This lets TTS start speaking the first sentence while the LLM
    generates the rest — cutting perceived latency dramatically.
    """
    DELIMITERS = {'.', '!', '?', '...', '\n'}

    def __init__(self):
        self.buffer = ""

    def feed(self, token: str) -> Optional[str]:
        self.buffer += token
        for delim in self.DELIMITERS:
            if delim in self.buffer:
                idx = self.buffer.index(delim) + len(delim)
                sentence = self.buffer[:idx].strip()
                self.buffer = self.buffer[idx:]
                if sentence:
                    return sentence
        return None

    def flush(self) -> Optional[str]:
        remainder = self.buffer.strip()
        self.buffer = ""
        return remainder if remainder else None


# ─────────────────────────────────────────────
# TTS — Fish Audio S2-Pro
# ─────────────────────────────────────────────

class FishAudioTTS:
    def __init__(self, cfg: SeishinConfig):
        self.cfg = cfg

    async def synthesize_stream(
        self, text: str, session: aiohttp.ClientSession
    ) -> AsyncGenerator[bytes, None]:
        """Streams audio chunks from Fish Audio."""
        url = f"{self.cfg.fish_audio_url}/v1/tts"
        payload = {
            "text": text,
            "reference_id": self.cfg.fish_reference_id,
            "format": "wav",
            "streaming": True,
            "normalize": True,
            "latency": "normal",  # use "balanced" for faster first-chunk
        }

        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"TTS error {resp.status}: {body}")
            async for chunk in resp.content.iter_chunked(4096):
                if chunk:
                    yield chunk

    async def synthesize_to_file(self, text: str, out_path: str, session: aiohttp.ClientSession):
        """Writes full audio to file (for testing)."""
        chunks = []
        async for chunk in self.synthesize_stream(text, session):
            chunks.append(chunk)
        with open(out_path, "wb") as f:
            f.write(b"".join(chunks))


# ─────────────────────────────────────────────
# Audio playback — streams PCM to speaker
# ─────────────────────────────────────────────

class AudioPlayer:
    def __init__(self, cfg: SeishinConfig):
        self.cfg = cfg
        self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._playing = False

    async def enqueue(self, audio_bytes: bytes):
        await self._queue.put(audio_bytes)

    async def stop(self):
        await self._queue.put(None)  # sentinel

    async def play_loop(self):
        """Continuously drains the queue and plays audio."""
        self._playing = True
        stream = sd.OutputStream(
            samplerate=self.cfg.sample_rate,
            channels=self.cfg.channels,
            dtype="int16",
        )
        stream.start()
        try:
            while True:
                chunk = await self._queue.get()
                if chunk is None:
                    break
                # Skip WAV header on first chunk if present
                pcm = self._strip_wav_header(chunk)
                if pcm:
                    arr = np.frombuffer(pcm, dtype=np.int16)
                    stream.write(arr)
        finally:
            stream.stop()
            stream.close()
            self._playing = False

    @staticmethod
    def _strip_wav_header(data: bytes) -> bytes:
        """Strip WAV header (44 bytes) if present."""
        if data[:4] == b"RIFF":
            return data[44:]
        return data


# ─────────────────────────────────────────────
# Dashboard WebSocket broadcaster
# ─────────────────────────────────────────────

class DashboardBroadcaster:
    def __init__(self, port: int):
        self.port = port
        self._clients: set = set()

    async def handler(self, websocket):
        self._clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)

    async def broadcast(self, event: dict):
        if not self._clients:
            return
        msg = json.dumps(event)
        await asyncio.gather(
            *[ws.send(msg) for ws in self._clients],
            return_exceptions=True,
        )

    async def start(self):
        server = await websockets.serve(self.handler, "0.0.0.0", self.port)
        log.info(f"Dashboard WS running on ws://localhost:{self.port}")
        return server


# ─────────────────────────────────────────────
# Main Pipeline
# ─────────────────────────────────────────────

class SeishinPipeline:
    def __init__(self, cfg: SeishinConfig):
        self.cfg = cfg
        self.stt = ParakeetSTT(cfg)
        self.llm = QwenLLM(cfg)
        self.tts = FishAudioTTS(cfg)
        self.player = AudioPlayer(cfg)
        self.vad = SimpleVAD(cfg)
        self.broadcaster = DashboardBroadcaster(cfg.ws_port)
        self._session: Optional[aiohttp.ClientSession] = None

    async def run(self):
        """Main entry point — starts all subsystems."""
        async with aiohttp.ClientSession() as session:
            self._session = session
            await self.broadcaster.start()

            log.info("🎙️  Seishin Phase 1 — Listening...")
            await self.broadcaster.broadcast({"type": "status", "state": "listening"})

            # Start audio player loop in background
            player_task = asyncio.create_task(self.player.play_loop())

            try:
                await self._mic_loop()
            finally:
                await self.player.stop()
                await player_task

    async def _mic_loop(self):
        """Captures mic, detects utterances via VAD, runs pipeline."""
        chunk_samples = int(self.cfg.sample_rate * self.cfg.chunk_duration_ms / 1000)
        audio_buffer: list[np.ndarray] = []

        loop = asyncio.get_event_loop()
        mic_queue: asyncio.Queue[np.ndarray] = asyncio.Queue()

        def mic_callback(indata, frames, time_info, status):
            loop.call_soon_threadsafe(mic_queue.put_nowait, indata.copy().flatten())

        with sd.InputStream(
            samplerate=self.cfg.sample_rate,
            channels=self.cfg.channels,
            blocksize=chunk_samples,
            dtype="float32",
            callback=mic_callback,
        ):
            while True:
                chunk = await mic_queue.get()
                vad_result = self.vad.process(chunk)

                if vad_result in ("speech", "end_of_utterance"):
                    audio_buffer.append(chunk)

                if vad_result == "end_of_utterance" and audio_buffer:
                    audio_np = np.concatenate(audio_buffer)
                    audio_buffer = []
                    asyncio.create_task(self._handle_utterance(audio_np))

    async def _handle_utterance(self, audio_np: np.ndarray):
        """Full pipeline for one utterance: STT → LLM → TTS → Speaker."""
        trace = LatencyTrace()

        try:
            # Encode audio to WAV bytes
            import io
            buf = io.BytesIO()
            sf.write(buf, audio_np, self.cfg.sample_rate, format="WAV", subtype="PCM_16")
            audio_bytes = buf.getvalue()

            # ── STT ──────────────────────────────────────
            await self.broadcaster.broadcast({"type": "status", "state": "transcribing"})
            user_text = await self.stt.transcribe(audio_bytes, self._session)
            trace.mark_stt()

            if not user_text:
                log.info("Empty transcription, skipping.")
                return

            log.info(f"[USER] {user_text}")
            await self.broadcaster.broadcast({
                "type": "transcript",
                "role": "user",
                "text": user_text,
                "latency": trace.report(),
            })

            # ── LLM → TTS (streaming, sentence-level) ───
            await self.broadcaster.broadcast({"type": "status", "state": "thinking"})
            chunker = SentenceChunker()
            full_response = []
            first_tts_done = False

            async for token in self.llm.stream(user_text, self._session):
                if not trace.llm_first_token:
                    trace.mark_llm()
                    await self.broadcaster.broadcast({
                        "type": "llm_first_token",
                        "latency": trace.report(),
                    })

                full_response.append(token)
                sentence = chunker.feed(token)

                if sentence:
                    await self._speak_sentence(sentence, self._session, trace, first_tts_done)
                    first_tts_done = True

            # Flush remaining buffer
            remainder = chunker.flush()
            if remainder:
                await self._speak_sentence(remainder, self._session, trace, first_tts_done)

            full_text = "".join(full_response)
            log.info(f"[SEISHIN] {full_text}")

            final_report = trace.report()
            log.info(f"⚡ Latency: {final_report}")
            await self.broadcaster.broadcast({
                "type": "transcript",
                "role": "assistant",
                "text": full_text,
                "latency": final_report,
            })
            await self.broadcaster.broadcast({"type": "status", "state": "listening"})

        except Exception as e:
            log.error(f"Pipeline error: {e}", exc_info=True)
            await self.broadcaster.broadcast({"type": "error", "message": str(e)})
            await self.broadcaster.broadcast({"type": "status", "state": "listening"})

    async def _speak_sentence(
        self,
        sentence: str,
        session: aiohttp.ClientSession,
        trace: LatencyTrace,
        tts_started: bool,
    ):
        """Synthesize one sentence and stream to speaker."""
        await self.broadcaster.broadcast({"type": "status", "state": "speaking"})
        async for audio_chunk in self.tts.synthesize_stream(sentence, session):
            if not tts_started and not trace.tts_first_audio:
                trace.mark_tts()
                report = trace.report()
                log.info(f"🔊 First audio chunk — total latency: {report['total_ms']}ms")
                await self.broadcaster.broadcast({
                    "type": "tts_first_audio",
                    "latency": report,
                })
            await self.player.enqueue(audio_chunk)


# ─────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────

async def main():
    cfg = SeishinConfig()
    pipeline = SeishinPipeline(cfg)
    await pipeline.run()


if __name__ == "__main__":
    asyncio.run(main())
