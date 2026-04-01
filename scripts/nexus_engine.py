import sys
import time
import json
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- CONFIGURATION ---
BRAIN_URL = "http://172.17.0.1:8001/v1/completions"
MODEL_NAME = "Qwen/Qwen3.5-9B"
LISTEN_PORT = 5050
PREFILL_TIMEOUT = 0.2

# --- CONVERSATION STATE ---
history = [
    ('User', 'Hello!'),
    ('Nexus', 'Systems online. I am awake and ready.'),
]

SYSTEM_PROMPT = (
    "Nexus is a knowledgeable, witty AI assistant. "
    "Nexus gives direct, informative answers in one or two sentences. "
    "Nexus never repeats or parrots the user's words back. "
    "Nexus never repeats its own previous responses."
)

DODGE_PHRASES = ['not sure', "don't know", 'no idea', 'database', 'glitch', 'cannot', "can't help"]

def build_prompt():
    lines = [SYSTEM_PROMPT]
    for role, text in history:
        lines.append(f'{role}: {text}')
    lines.append('Nexus:')
    return '\n'.join(lines)

def prefill_brain(partial_text):
    """Warm vLLM's KV prefix cache with partial transcript."""
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

        reply = ''.join(reply_parts).strip()
        if reply and len(reply) >= 10 and not any(p in reply.lower() for p in DODGE_PHRASES):
            history.append(('Nexus', reply))
        else:
            history.pop()

    except Exception as e:
        print(f"\nBrain connection failed: {e}\n")
        history.pop()

# --- HTTP SERVER ---
class NexusHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == '/prefill':
            self.send_response(200)
            self.end_headers()
            text = body.get('text', '')
            if text:
                threading.Thread(target=prefill_brain, args=(text,), daemon=True).start()

        elif self.path == '/flush':
            self.send_response(200)
            self.end_headers()
            text = body.get('text', '')
            asr_ttft = body.get('asr_ttft')
            speech_elapsed = body.get('speech_elapsed')
            if asr_ttft is not None and speech_elapsed is not None:
                print(f'\033[90m[ASR TTFT: {asr_ttft:.0f}ms | speech: {speech_elapsed:.0f}ms]\033[0m')
            if text:
                ask_brain(text)

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default HTTP access logs

def main():
    server = HTTPServer(('0.0.0.0', LISTEN_PORT), NexusHandler)
    print(f'NEXUS ENGINE ONLINE — listening on port {LISTEN_PORT}')
    print(f'Brain: {BRAIN_URL}')
    print(f'Model: {MODEL_NAME}')
    print('Waiting for ears daemon...\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nNexus engine shutting down...')
        server.server_close()

if __name__ == '__main__':
    main()
