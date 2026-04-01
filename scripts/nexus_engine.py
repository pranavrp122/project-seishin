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

# --- CONFIGURATION ---
# 172.17.0.1 is the Docker bridge IP to reach the vLLM container
BRAIN_URL = 'http://172.17.0.1:8001/v1/completions'
MODEL_NAME = 'Qwen/Qwen3.5-9B'
SILENCE_THRESHOLD = 1.3

print('👂 Initializing Parakeet TDT 1.1b...')
model = nemo_asr.models.ASRModel.from_pretrained('nvidia/parakeet-tdt-1.1b')
model.cuda().eval()

RATE = 16000
audio_queue = queue.Queue()

def callback(indata, frames, time, status):
    if status: print(status, file=sys.stderr)
    audio_queue.put(indata.copy())

def ask_brain(text):
    # This Few-Shot pattern forces the Base model to behave and skip the essay
    prompt_template = (
        f'The following is a conversation with the Nexus Engine, a witty AI.\n'
        f'User: Hello!\n'
        f'Nexus Engine: Systems online. I am awake and ready.\n'
        f'User: {text}\n'
        f'Nexus Engine:'
    )

    try:
        response = requests.post(
            BRAIN_URL,
            json={
                'model': MODEL_NAME,
                'prompt': prompt_template,
                'max_tokens': 300,
                'temperature': 0.7,
                'stop': ['User:', '\n'],
                'stream': True
            },
            stream=True,
            timeout=10
        )

        print('\r✨ Nexus Engine: ', end='', flush=True)
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    if '[DONE]' in line: break
                    chunk = json.loads(line[6:])
                    content = chunk['choices'][0].get('text', '')
                    print(content, end='', flush=True)
        print('\n')

    except Exception as e:
        print(f'\n❌ Brain connection failed: {e}\n')

print('\n🚀 NEXUS ENGINE UPDATED. Speak into the mic. Press ENTER to send to the brain. (Ctrl+C to stop)\n')

send_trigger = threading.Event()
def wait_for_enter():
    while True:
        sys.stdin.readline()
        send_trigger.set()

threading.Thread(target=wait_for_enter, daemon=True).start()

def run_live():
    buffer = np.zeros(0, dtype=np.float32)
    last_text = ''

    try:
        with sd.InputStream(samplerate=RATE, channels=1, callback=callback, blocksize=800):
            while True:
                while not audio_queue.empty():
                    buffer = np.append(buffer, audio_queue.get().flatten())

                if len(buffer) < 1600: continue

                audio_signal = torch.from_numpy(buffer).cuda().float()
                with torch.no_grad():
                    log_probs, log_probs_len = model.forward(
                        input_signal=audio_signal.unsqueeze(0),
                        input_signal_length=torch.tensor([audio_signal.shape[0]]).cuda()
                    )

                    hypotheses = model.decoding.rnnt_decoder_predictions_tensor(log_probs, log_probs_len)
                    if isinstance(hypotheses, tuple): hypotheses = hypotheses[0]
                    tokens = hypotheses[0].y_sequence

                    if torch.is_tensor(tokens): tokens = tokens.cpu().numpy().tolist()
                    elif isinstance(tokens, list) and len(tokens) > 0 and torch.is_tensor(tokens[0]):
                        tokens = [t.item() for t in tokens]

                    text = model.tokenizer.ids_to_text(tokens).strip()

                if text:
                    if text != last_text:
                        last_text = text
                        print(f'\r🎤 Hearing: {text}    ', end='', flush=True)

                    if send_trigger.is_set():
                        send_trigger.clear()
                        if len(text) > 2:
                            print('\n')
                            ask_brain(text)
                        buffer = np.zeros(0, dtype=np.float32)
                        last_text = ''
                        print('\n👂 Listening...', end='', flush=True)
                        while not audio_queue.empty(): audio_queue.get()

    except KeyboardInterrupt:
        print('\n\n👋 Shutting down...')

if __name__ == '__main__':
    run_live()
