import nemo.collections.asr as nemo_asr
import numpy as np
import sounddevice as sd
import torch
import sys
import queue
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

def build_prompt():
    lines = ['The following is a conversation with Nexus, a witty AI.']
    for role, text in history:
        lines.append(f'{role}: {text}')
    lines.append('Nexus:')
    return '\n'.join(lines)

def ask_brain(text):
    history.append(('User', text))
    prompt = build_prompt()
    reply_parts = []

    print(f"\nSending to 5090...")
    try:
        response = requests.post(
            BRAIN_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "max_tokens": 300,
                "temperature": 0.7,
                "stop": ["User:", "\n"],
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
                            reply_parts.append(content)
                            print(content, end="", flush=True)
                    except json.JSONDecodeError:
                        continue
        print("\n")

        # Store reply in history so future turns have context
        reply = ''.join(reply_parts).strip()
        if reply:
            history.append(('Nexus', reply))

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
                        last_text = text
                        print(f'\r> {text}    ', end='', flush=True)

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
                            print(f'\r> {text}    ')
                            ask_brain(text)

                    # Reset all state
                    asr_buffer = np.zeros(0, dtype=np.float32)
                    vad_accumulator = np.zeros(0, dtype=np.float32)
                    pre_buffer.clear()
                    speech_frame_count = 0
                    silence_counter = 0
                    last_text = ''
                    state = 'IDLE'
                    vad_model.reset_states()
                    while not audio_queue.empty():
                        audio_queue.get()
                    print('\nListening...', end='', flush=True)

    except KeyboardInterrupt:
        print('\n\nShutting down...')

if __name__ == '__main__':
    run_live()
