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

# --- CONFIGURATION ---
BRAIN_URL = "http://172.17.0.1:8001/v1/completions"  # FIXED: Removed /chat/
MODEL_NAME = "Qwen/Qwen3.5-9B"

print("👂 Initializing Parakeet TDT 1.1b...")
model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-1.1b")
model.cuda().eval()

RATE = 16000
audio_queue = queue.Queue()

def callback(indata, frames, time, status):
    if status: print(status, file=sys.stderr)
    audio_queue.put(indata.copy())

def ask_brain(text):
    prompt_template = (
        "Context: The Nexus Engine is a witty, localized AI companion.\n"
        "User: Hi there.\n"
        "Nexus Engine: Systems online. What's on your mind?\n"
        "User: Are you awake?\n"
        "Nexus Engine: Always. My processors are primed and ready for you.\n"
        f"User: {text}\n"
        "Nexus Engine:"
    )

    print(f"\n🧠 Sending to 5090...")
    try:
        response = requests.post(
            BRAIN_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt_template,
                "max_tokens": 300,
                "temperature": 0.8,
                "stop": ["User:", "\n"],
                "stream": True
            },
            stream=True,
            timeout=60
        )

        # FIXED: Added status check to prevent silent failures
        if response.status_code != 200:
            print(f"\n❌ Brain Error {response.status_code}: {response.text}")
            return

        print("✨ Nexus Engine: ", end="", flush=True)
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        # FIXED: Explicitly grabs 'text' for base models
                        content = chunk['choices'][0].get('text', '')
                        print(content, end="", flush=True)
                    except json.JSONDecodeError:
                        continue
        print("\n")

    except Exception as e:
        print(f"\n❌ Brain connection failed: {e}\n")

# --- ENTER KEY TRIGGER ---
print('\n🚀 NEXUS ENGINE ONLINE. Speak into the mic. Press ENTER to send. (Ctrl+C to stop)\n')

send_trigger = threading.Event()
def _wait_for_enter():
    while True:
        sys.stdin.readline()
        send_trigger.set()
threading.Thread(target=_wait_for_enter, daemon=True).start()

def run_live():
    buffer = np.zeros(0, dtype=np.float32)
    last_text = ''

    print('👂 Listening...', end='', flush=True)

    try:
        with sd.InputStream(samplerate=RATE, channels=1, callback=callback, blocksize=800):
            while True:
                while not audio_queue.empty():
                    buffer = np.append(buffer, audio_queue.get().flatten())

                if len(buffer) < 1600:
                    continue

                try:
                    with contextlib.redirect_stderr(io.StringIO()):
                        results = model.transcribe([buffer], batch_size=1, verbose=False)
                    # transcribe() returns list of strings or Hypothesis objects
                    if results:
                        r = results[0]
                        text = r.text if hasattr(r, 'text') else str(r)
                        text = text.strip()
                    else:
                        text = ''
                except Exception as asr_err:
                    print(f'\r⚠ ASR error: {asr_err}   ', end='', flush=True)
                    text = ''

                if text and text != last_text:
                    last_text = text
                    print(f'\r🎤 {text}    ', end='', flush=True)

                # Only send on Enter, no silence threshold
                if send_trigger.is_set():
                    send_trigger.clear()
                    if last_text and len(last_text) > 2:
                        print('\n')
                        ask_brain(last_text)
                    buffer = np.zeros(0, dtype=np.float32)
                    last_text = ''
                    while not audio_queue.empty(): audio_queue.get()
                    print('\n👂 Listening...', end='', flush=True)

    except KeyboardInterrupt:
        print('\n\n👋 Shutting down...')

if __name__ == '__main__':
    run_live()