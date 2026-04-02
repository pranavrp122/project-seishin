import torch
torch.cuda.set_per_process_memory_fraction(0.15, 0)  # Hard VRAM cap: ~4.8 GB

"""Mouth Daemon — Hybrid Qwen3-TTS (CUDA Graph + Triton fusion) with PulseAudio playback.

Uses qwen3-tts-triton TritonFasterRunner for ~4.7x speedup over baseline.
Architecture: Main thread (HTTP server :5051) + TTS worker thread + audio callback.
"""

import os
import re
import json
import queue
import threading
import numpy as np
import sounddevice as sd
from math import gcd
from http.server import HTTPServer, BaseHTTPRequestHandler
from scipy.signal import resample_poly

from qwen3_tts_triton import TritonFasterRunner

# --- CONFIGURATION ---
LISTEN_PORT = 5051
PLAYBACK_SR = 48000
BLOCKSIZE = 4800  # 100ms at 48kHz

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
    g = gcd(PLAYBACK_SR, src_rate)
    up, down = PLAYBACK_SR // g, src_rate // g
    return resample_poly(pcm, up, down).astype(pcm.dtype)


def float32_to_int16(audio):
    """Convert float32 [-1, 1] audio to int16."""
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767).astype(np.int16)


# --- SHARED STATE ---
text_queue = queue.Queue()
audio_queue = queue.Queue()
stop_event = threading.Event()
_leftover = bytearray()


# --- AUDIO CALLBACK ---
def audio_callback(outdata, frames, time_info, status):
    """Pull audio from audio_queue into the output buffer. Keeps leftover bytes between calls."""
    global _leftover
    bytes_needed = frames * 2  # int16 = 2 bytes per sample
    buf = _leftover
    while len(buf) < bytes_needed:
        try:
            chunk = audio_queue.get_nowait()
            buf.extend(chunk)
        except queue.Empty:
            break
    if len(buf) >= bytes_needed:
        outdata[:] = bytes(buf[:bytes_needed])
        _leftover = bytearray(buf[bytes_needed:])
    else:
        outdata[:len(buf)] = bytes(buf)
        outdata[len(buf):] = b'\x00' * (bytes_needed - len(buf))
        _leftover = bytearray()


# --- TTS WORKER ---
def tts_worker(runner, speaker):
    """Consume text_queue, synthesize via Hybrid streaming, push audio to audio_queue."""
    while True:
        text = text_queue.get()
        if text is None:
            break

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
                audio_queue.put(resampled.tobytes())
        except Exception as e:
            print(f"[mouth] TTS error: {e}")


# --- DRAIN HELPER ---
def drain_queues():
    """Drain text queue, audio queue, and leftover buffer."""
    global _leftover
    for q in (text_queue, audio_queue):
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break
    _leftover = bytearray()


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
                text_queue.put(text)

        elif self.path == '/stop':
            self.send_response(200)
            self.end_headers()
            stop_event.set()
            drain_queues()

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default HTTP access logs


# --- MAIN ---
def main():
    print("Loading Hybrid Qwen3-TTS (CUDA Graph + Triton)...")
    runner = TritonFasterRunner(dtype="bf16")
    runner.load_model()
    print("Hybrid Qwen3-TTS loaded")

    speaker = os.environ.get("TTS_SPEAKER", "Aiden")

    # Start audio output stream
    stream = sd.RawOutputStream(
        samplerate=PLAYBACK_SR,
        channels=1,
        dtype='int16',
        blocksize=BLOCKSIZE,
        latency='high',
        callback=audio_callback,
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
