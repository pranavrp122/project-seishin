import torch
torch.cuda.set_per_process_memory_fraction(0.18, 0)  # Hard VRAM cap: ~5.9 GB

"""Mouth Daemon — Hybrid Qwen3-TTS (CUDA Graph + Triton fusion) with PulseAudio playback.

Uses qwen3-tts-triton TritonFasterRunner for ~4.7x speedup over baseline.
Architecture: Main thread (HTTP server :5051) + TTS worker thread + blocking audio writes.
"""

import gc
import os
import re
import json
import queue
import threading
import numpy as np
import sounddevice as sd
from math import gcd
from http.server import HTTPServer, BaseHTTPRequestHandler
from scipy.signal import resample_poly, firwin, upfirdn

from qwen3_tts_triton import TritonFasterRunner

# --- CONFIGURATION ---
LISTEN_PORT = 5051
PLAYBACK_SR = 48000
BLOCKSIZE = 4800  # 100ms at 48kHz
RUNNER_RELOAD_INTERVAL = 5  # Reload runner every N generations to reset CUDA graph state

# --- PRE-COMPUTED RESAMPLER (24kHz → 48kHz) ---
_RESAMPLE_UP = 2
_RESAMPLE_DOWN = 1
_RESAMPLE_TAPS = firwin(20 * _RESAMPLE_UP + 1, 1.0 / _RESAMPLE_UP, window=('kaiser', 5.0))

# --- EMOTION PARSER ---
DEFAULT_INSTRUCT = "Speak in a warm, friendly voice"
EMOTION_RE = re.compile(r'^\((\w[\w\s]*)\)\s*')


def parse_emotion(text):
    """Extract (emotion) prefix -> instruct string. Return (instruct, clean_text)."""
    m = EMOTION_RE.match(text)
    if m:
        emotion = m.group(1).strip()
        clean = text[m.end():]
        return f"Speak in a {emotion} voice", clean
    return DEFAULT_INSTRUCT, text


# --- RESAMPLER ---
def resample_to_48k(pcm, src_rate):
    """Resample PCM audio from src_rate to 48000 Hz."""
    if src_rate == PLAYBACK_SR:
        return pcm
    if src_rate == 24000:
        return upfirdn(_RESAMPLE_TAPS, pcm, _RESAMPLE_UP, _RESAMPLE_DOWN).astype(pcm.dtype)
    g = gcd(PLAYBACK_SR, src_rate)
    up, down = PLAYBACK_SR // g, src_rate // g
    return resample_poly(pcm, up, down).astype(pcm.dtype)


def float32_to_int16(audio):
    """Convert float32 [-1, 1] audio to int16."""
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767).astype(np.int16)


# --- SHARED STATE ---
text_queue = queue.Queue(maxsize=3)
stop_event = threading.Event()
worker_idle = threading.Event()
worker_idle.set()
stream = None  # Initialized in main(); used by tts_worker (write) and /stop (abort)
_generation_count = 0


# --- TTS WORKER ---
def tts_worker(runner, speaker):
    """Consume text_queue, synthesize via Hybrid streaming, write audio to output stream."""
    global _generation_count
    while True:
        worker_idle.set()
        text = text_queue.get()
        if text is None:
            break

        worker_idle.clear()
        stop_event.clear()

        instruct, clean_text = parse_emotion(text)
        if not clean_text.strip():
            continue

        try:
            for audio_chunk, sr, timing in runner.generate_streaming(
                text=clean_text,
                language="English",
                speaker=speaker,
                instruct=instruct,
                chunk_size=4,
            ):
                if stop_event.is_set():
                    break
                audio_int16 = float32_to_int16(audio_chunk)
                resampled = resample_to_48k(audio_int16, sr)
                try:
                    stream.write(resampled.tobytes())
                except Exception:
                    break  # Stream aborted by /stop
        except Exception as e:
            print(f"[mouth] TTS error: {e}")
        finally:
            _generation_count += 1
            gc.collect()
            torch.cuda.empty_cache()
            alloc = torch.cuda.memory_allocated() / 1024**2
            reserved = torch.cuda.memory_reserved() / 1024**2
            print(f"[mouth] gen #{_generation_count} | VRAM: {alloc:.0f}MB alloc / {reserved:.0f}MB reserved")

            if _generation_count % RUNNER_RELOAD_INTERVAL == 0:
                print(f"[mouth] Reloading runner to reset CUDA graph state...")
                runner.unload_model()
                gc.collect()
                torch.cuda.empty_cache()
                runner.load_model()
                print(f"[mouth] Runner reloaded.")


# --- DRAIN HELPER ---
def drain_text_queue():
    """Drain pending text from the queue."""
    while not text_queue.empty():
        try:
            text_queue.get_nowait()
        except queue.Empty:
            break


# --- HTTP SERVER ---
class MouthHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == '/speak':
            self.send_response(200)
            self.end_headers()
            text = body.get('text', '')
            if text:
                try:
                    text_queue.put_nowait(text)
                except queue.Full:
                    pass  # Drop — TTS is behind, sentence is stale

        elif self.path == '/stop':
            self.send_response(200)
            self.end_headers()
            stop_event.set()
            stream.abort()
            worker_idle.wait(timeout=0.5)
            stream.start()
            drain_text_queue()

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default HTTP access logs


# --- MAIN ---
def main():
    global stream
    print("Loading Hybrid Qwen3-TTS (CUDA Graph + Triton)...")
    runner = TritonFasterRunner(dtype="bf16")
    runner.load_model()
    print("Hybrid Qwen3-TTS loaded")

    speaker = os.environ.get("TTS_SPEAKER", "Aiden")

    # Start audio output stream (blocking write mode — no callback)
    stream = sd.RawOutputStream(
        samplerate=PLAYBACK_SR,
        channels=1,
        dtype='int16',
        blocksize=BLOCKSIZE,
        latency='high',
    )
    stream.start()

    # Start TTS worker thread
    worker = threading.Thread(
        target=tts_worker,
        args=(runner, speaker),
        daemon=True,
    )
    worker.start()

    # Start HTTP server
    server = HTTPServer(('0.0.0.0', LISTEN_PORT), MouthHandler)
    print(f"Listening on :{LISTEN_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMouth daemon shutting down...")
        stop_event.set()
        text_queue.put(None)  # Unblock worker
        stream.stop()
        stream.close()
        runner.unload_model()
        server.server_close()


if __name__ == '__main__':
    main()
