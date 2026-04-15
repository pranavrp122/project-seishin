import torch
torch.cuda.set_per_process_memory_fraction(0.35, 0)  # ~11.2 GB cap for Fish Speech S2 Pro

"""Mouth Daemon — Fish Speech S2 Pro with PulseAudio playback.

Direct import of Fish Speech inference engine for lowest latency.
Architecture: Main thread (HTTP server :5051) + TTS worker thread + blocking audio writes.
Fish Speech repo stays independent — this daemon is a consumer, not a fork.
"""

import gc
import os
import re
import json
import queue
import threading
import numpy as np
import sounddevice as sd
from http.server import HTTPServer, BaseHTTPRequestHandler

from fish_speech.inference_engine import TTSInferenceEngine
from fish_speech.models.dac.inference import load_model as load_decoder_model
from fish_speech.models.text2semantic.inference import launch_thread_safe_queue
from fish_speech.utils.schema import ServeTTSRequest

# --- CONFIGURATION ---
LISTEN_PORT = 5051
PLAYBACK_SR = 44100  # Fish Speech S2 Pro native rate — no resampling needed
BLOCKSIZE = 4410  # 100ms at 44.1kHz

# Fish Speech config (override via env vars)
LLAMA_CHECKPOINT = os.environ.get("LLAMA_CHECKPOINT", "checkpoints/s2-pro")
DECODER_CHECKPOINT = os.environ.get("DECODER_CHECKPOINT", "checkpoints/s2-pro/codec.pth")
DECODER_CONFIG = os.environ.get("DECODER_CONFIG", "modded_dac_vq")
REFERENCE_ID = os.environ.get("TTS_REFERENCE_ID", "archie")
COMPILE = os.environ.get("COMPILE", "1") in ("1", "true", "True")

# TTS generation params
TTS_TOP_P = float(os.environ.get("TTS_TOP_P", "0.8"))
TTS_TEMPERATURE = float(os.environ.get("TTS_TEMPERATURE", "0.8"))
TTS_REPETITION_PENALTY = float(os.environ.get("TTS_REPETITION_PENALTY", "1.1"))
TTS_MAX_NEW_TOKENS = int(os.environ.get("TTS_MAX_NEW_TOKENS", "1024"))
TTS_CHUNK_LENGTH = int(os.environ.get("TTS_CHUNK_LENGTH", "300"))

# --- EMOTION PARSER ---
# LLM emits (emotion) prefix — convert to Fish Speech [emotion] tag
EMOTION_RE = re.compile(r'^\((\w[\w\s]*)\)\s*')


def parse_emotion(text):
    """Convert (emotion) prefix to [emotion] tag for Fish Speech."""
    m = EMOTION_RE.match(text)
    if m:
        emotion = m.group(1).strip()
        clean = text[m.end():]
        return f"[{emotion}] {clean}"
    return text


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


# --- TTS WORKER ---
def tts_worker(engine):
    """Consume text_queue, synthesize via Fish Speech streaming, write audio to output stream."""
    while True:
        worker_idle.set()
        text = text_queue.get()
        if text is None:
            break

        worker_idle.clear()
        stop_event.clear()

        # Convert (emotion) prefix to [emotion] tag
        clean_text = parse_emotion(text)
        if not clean_text.strip():
            continue

        req = ServeTTSRequest(
            text=clean_text,
            references=[],
            reference_id=REFERENCE_ID,
            max_new_tokens=TTS_MAX_NEW_TOKENS,
            chunk_length=TTS_CHUNK_LENGTH,
            top_p=TTS_TOP_P,
            repetition_penalty=TTS_REPETITION_PENALTY,
            temperature=TTS_TEMPERATURE,
            streaming=True,
            use_memory_cache="on",
        )

        try:
            for result in engine.inference(req):
                if stop_event.is_set():
                    break

                if result.code == "header":
                    continue  # Skip WAV header — raw PCM to sounddevice
                elif result.code == "error":
                    print(f"[mouth] TTS error: {result.error}")
                    break
                elif result.code in ("segment", "final"):
                    if result.audio is None:
                        continue
                    sr, audio_data = result.audio
                    if not isinstance(audio_data, np.ndarray) or len(audio_data) == 0:
                        continue
                    # Engine yields float32 segments; final may also be float32
                    if audio_data.dtype in (np.float32, np.float64):
                        audio_int16 = float32_to_int16(audio_data)
                    else:
                        audio_int16 = audio_data.astype(np.int16)
                    try:
                        stream.write(audio_int16.tobytes())
                    except Exception:
                        break  # Stream aborted by /stop
        except Exception as e:
            print(f"[mouth] TTS error: {e}")
        finally:
            gc.collect()
            torch.cuda.empty_cache()
            alloc = torch.cuda.memory_allocated() / 1024**2
            reserved = torch.cuda.memory_reserved() / 1024**2
            print(f"[mouth] VRAM: {alloc:.0f}MB alloc / {reserved:.0f}MB reserved")


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

    print("Loading Fish Speech S2 Pro (INT8 + TF32 + torch.compile)...")

    precision = torch.bfloat16
    device = "cuda"

    # Load LLaMA text-to-semantic model (INT8 quant + TF32 + compile applied inside)
    llama_queue = launch_thread_safe_queue(
        checkpoint_path=LLAMA_CHECKPOINT,
        device=device,
        precision=precision,
        compile=COMPILE,
    )

    # Load DAC decoder model
    decoder_model = load_decoder_model(
        config_name=DECODER_CONFIG,
        checkpoint_path=DECODER_CHECKPOINT,
        device=device,
    )

    # Create inference engine
    engine = TTSInferenceEngine(
        llama_queue=llama_queue,
        decoder_model=decoder_model,
        precision=precision,
        compile=COMPILE,
    )

    # Warm up models + reference cache
    print("Warming up...")
    warmup_req = ServeTTSRequest(
        text="Hello.",
        references=[],
        reference_id=REFERENCE_ID,
        max_new_tokens=TTS_MAX_NEW_TOKENS,
        chunk_length=200,
        top_p=0.7,
        repetition_penalty=1.2,
        temperature=0.7,
        format="wav",
        use_memory_cache="on",
    )
    list(engine.inference(warmup_req))
    print("Fish Speech S2 Pro loaded and warmed up")

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
        args=(engine,),
        daemon=True,
    )
    worker.start()

    # Start HTTP server
    server = HTTPServer(('127.0.0.1', LISTEN_PORT), MouthHandler)
    print(f"Listening on :{LISTEN_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMouth daemon shutting down...")
        stop_event.set()
        text_queue.put(None)  # Unblock worker
        stream.stop()
        stream.close()
        server.server_close()


if __name__ == '__main__':
    main()
