import nemo.collections.asr as nemo_asr
import numpy as np
import sounddevice as sd
import torch
import sys
import queue
import threading
import time
import requests
import json
import contextlib
import io
from collections import deque

# --- CONFIGURATION ---
BRAIN_URL = "http://172.17.0.1:8001/v1/completions"  # FIXED: Removed /chat/
MODEL_NAME = "Qwen/Qwen3.5-9B"

# --- VAD PARAMETERS ---
VAD_CHUNK_SAMPLES = 512       # Silero requires exactly 512 samples at 16kHz
VAD_SPEECH_THRESHOLD = 0.5    # Speech probability threshold
VAD_SILENCE_FRAMES = 15       # 15 * 32ms = ~480ms of silence -> end of utterance
VAD_MIN_SPEECH_FRAMES = 5     # Ignore bursts < 5 frames (~160ms); filters clicks
VAD_MAX_BUFFER_SECONDS = 10   # Hard cap on ASR buffer

# --- SPECULATIVE PREFILL ---
PREFILL_WORD_THRESHOLD = 4    # Send prefill every 4 new words
PREFILL_TIMEOUT = 0.2         # 200ms timeout — never hangs main loop

RATE = 16000
audio_queue = queue.Queue()

# --- MODEL LOADING ---
print("Initializing Parakeet TDT 1.1b...")
model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-1.1b")
model.cuda().eval()

print("Loading Silero VAD...")
VAD_MODEL_PATH = '/root/.cache/torch/hub/snakers4_silero-vad_master/src/silero_vad/data/silero_vad.jit'
vad_model = torch.jit.load(VAD_MODEL_PATH, map_location='cpu')
vad_model.eval()

def callback(indata, frames, time, status):
    if status: print(status, file=sys.stderr)
    audio_queue.put(indata.copy())

# Conversation history seeded with opening exchange to keep Nexus in character
history = [
    ('User', 'Hello!'),
    ('Nexus', 'Systems online. I am awake and ready.'),
]

SYSTEM_PROMPT = (
    "Nexus is a knowledgeable, witty AI assistant. "
    "Nexus gives direct, informative answers. "
    "Nexus never repeats or parrots the user's words back. "
    "Nexus never repeats its own previous responses."
)

def build_prompt():
    lines = [SYSTEM_PROMPT]
    for role, text in history:
        lines.append(f'{role}: {text}')
    lines.append('Nexus:')
    return '\n'.join(lines)

def prefill_brain(partial_text):
    """Warm vLLM's KV prefix cache with partial transcript. Non-blocking."""
    history_copy = list(history)
    history_copy.append(('User', partial_text))
    lines = [SYSTEM_PROMPT]
    for role, text in history_copy:
        lines.append(f'{role}: {text}')
    lines.append('Nexus:')
    prompt = '\n'.join(lines)
    try:
        requests.post(
            BRAIN_URL,
            json={"model": MODEL_NAME, "prompt": prompt, "max_tokens": 1, "temperature": 0},
            timeout=PREFILL_TIMEOUT
        )
    except Exception:
        pass

def ask_brain(text):
    history.append(('User', text))
    prompt = build_prompt()
    reply_parts = []

    print(f"\nSending to 5090...")
    try:
        t0 = time.perf_counter()
        first_token = True
        ttft = None
        response = requests.post(
            BRAIN_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "max_tokens": 300,
                "temperature": 0.7,
                "repetition_penalty": 1.15,
                "stop": ["User:", "\n\n"],
                "stream": True
            },
            stream=True,
            timeout=60
        )

        # FIXED: Added status check to prevent silent failures
        if response.status_code != 200:
            print(f"\nBrain Error {response.status_code}: {response.text}")
            history.pop()
            return

        print("Nexus Engine: ", end="", flush=True)
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        # FIXED: Explicitly grabs 'text' for base models
                        content = chunk['choices'][0].get('text', '')
                        if content:
                            if first_token:
                                ttft = (time.perf_counter() - t0) * 1000
                                first_token = False
                            reply_parts.append(content)
                            print(content, end="", flush=True)
                    except json.JSONDecodeError:
                        continue
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"\n\033[90m[LLM TTFT: {ttft:.0f}ms | total: {elapsed:.0f}ms]\033[0m\n" if ttft else "\n")

        # Store reply in history — but filter out garbage to prevent history poisoning
        reply = ''.join(reply_parts).strip()
        DODGE_PHRASES = ['not sure', "don't know", 'no idea', 'database', 'glitch', 'cannot', "can't help"]
        if reply and len(reply) >= 10 and not any(p in reply.lower() for p in DODGE_PHRASES):
            history.append(('Nexus', reply))
        else:
            # Bad response — drop the user turn too so history stays clean
            history.pop()

    except Exception as e:
        print(f"\nBrain connection failed: {e}\n")
        history.pop()

# --- VAD STATE MACHINE ---
print('\nNEXUS ENGINE ONLINE. Hands-free VAD mode. (Ctrl+C to stop)\n')

def run_live():
    # State
    state = 'IDLE'
    asr_buffer = np.zeros(0, dtype=np.float32)
    vad_accumulator = np.zeros(0, dtype=np.float32)
    pre_buffer = deque(maxlen=VAD_MIN_SPEECH_FRAMES)
    speech_frame_count = 0
    silence_counter = 0
    last_text = ''
    last_prefill_word_count = 0
    speech_start_time = None
    asr_ttft = None

    print('Listening...', end='', flush=True)

    try:
        with sd.InputStream(samplerate=RATE, channels=1, callback=callback, blocksize=800):
            while True:
                # Drain audio queue into vad_accumulator
                drained = False
                while not audio_queue.empty():
                    vad_accumulator = np.append(vad_accumulator, audio_queue.get().flatten())
                    drained = True

                if not drained and len(vad_accumulator) < VAD_CHUNK_SAMPLES:
                    time.sleep(0.01)
                    continue

                # Process all available 512-sample chunks through Silero
                while len(vad_accumulator) >= VAD_CHUNK_SAMPLES:
                    chunk = vad_accumulator[:VAD_CHUNK_SAMPLES]
                    vad_accumulator = vad_accumulator[VAD_CHUNK_SAMPLES:]

                    # Silero on CPU - convert numpy to torch float tensor
                    chunk_tensor = torch.FloatTensor(chunk)
                    speech_prob = vad_model(chunk_tensor, RATE).item()

                    if state == 'IDLE':
                        pre_buffer.append(chunk)
                        if speech_prob > VAD_SPEECH_THRESHOLD:
                            speech_frame_count += 1
                            if speech_frame_count >= VAD_MIN_SPEECH_FRAMES:
                                state = 'SPEAKING'
                                speech_start_time = time.perf_counter()
                                asr_ttft = None
                                asr_buffer = np.concatenate(list(pre_buffer))
                                pre_buffer.clear()
                                silence_counter = 0
                        else:
                            speech_frame_count = 0

                    elif state == 'SPEAKING':
                        asr_buffer = np.append(asr_buffer, chunk)
                        if speech_prob <= VAD_SPEECH_THRESHOLD:
                            state = 'TRAILING'
                            silence_counter = 1

                    elif state == 'TRAILING':
                        asr_buffer = np.append(asr_buffer, chunk)
                        if speech_prob > VAD_SPEECH_THRESHOLD:
                            state = 'SPEAKING'
                            silence_counter = 0
                        else:
                            silence_counter += 1

                # Max buffer guard
                if len(asr_buffer) > VAD_MAX_BUFFER_SECONDS * RATE:
                    state = 'FLUSH'

                if state == 'TRAILING' and silence_counter >= VAD_SILENCE_FRAMES:
                    state = 'FLUSH'

                # Live transcription while speaking/trailing
                if state in ('SPEAKING', 'TRAILING') and len(asr_buffer) >= 1600:
                    try:
                        with contextlib.redirect_stderr(io.StringIO()):
                            results = model.transcribe([asr_buffer], batch_size=1, verbose=False)
                        if results:
                            r = results[0]
                            text = r.text if hasattr(r, 'text') else str(r)
                            text = text.strip()
                        else:
                            text = ''
                    except Exception as asr_err:
                        print(f'\rASR error: {asr_err}   ', end='', flush=True)
                        text = ''

                    if text and text != last_text:
                        if asr_ttft is None and speech_start_time:
                            asr_ttft = (time.perf_counter() - speech_start_time) * 1000
                        last_text = text
                        print(f'\r> {text}    ', end='', flush=True)
                        # Speculative prefill: warm KV cache every 4 new words
                        word_count = len(text.split())
                        if word_count >= last_prefill_word_count + PREFILL_WORD_THRESHOLD:
                            last_prefill_word_count = word_count
                            threading.Thread(target=prefill_brain, args=(text,), daemon=True).start()

                # Flush - final transcription + send to brain
                if state == 'FLUSH':
                    if len(asr_buffer) >= 1600:
                        try:
                            with contextlib.redirect_stderr(io.StringIO()):
                                results = model.transcribe([asr_buffer], batch_size=1, verbose=False)
                            if results:
                                r = results[0]
                                text = r.text if hasattr(r, 'text') else str(r)
                                text = text.strip()
                            else:
                                text = ''
                        except Exception as asr_err:
                            print(f'\rASR error: {asr_err}   ', end='', flush=True)
                            text = ''

                        if text and len(text) > 2:
                            speech_elapsed = (time.perf_counter() - speech_start_time) * 1000 if speech_start_time else 0
                            print(f'\r> {text}    ')
                            print(f'\033[90m[ASR TTFT: {asr_ttft:.0f}ms | speech: {speech_elapsed:.0f}ms]\033[0m')
                            ask_brain(text)

                    # Reset all state
                    asr_buffer = np.zeros(0, dtype=np.float32)
                    vad_accumulator = np.zeros(0, dtype=np.float32)
                    pre_buffer.clear()
                    speech_frame_count = 0
                    silence_counter = 0
                    last_text = ''
                    last_prefill_word_count = 0
                    speech_start_time = None
                    asr_ttft = None
                    state = 'IDLE'
                    vad_model.reset_states()
                    while not audio_queue.empty():
                        audio_queue.get()
                    print('\nListening...', end='', flush=True)

    except KeyboardInterrupt:
        print('\n\nShutting down...')

if __name__ == '__main__':
    run_live()
