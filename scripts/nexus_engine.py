import sys
import time
import json
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from system_prompts import SYSTEM_PROMPT, SEED_HISTORY, DODGE_PHRASES
from report_generation import is_report_request, run_report_pipeline
from report_generation.write_spoken_report import write_spoken_report_output
import re
MOUTH_URL = "http://172.17.0.1:5051"

# --- CONFIGURATION ---
BRAIN_URL = "http://172.17.0.1:8001/v1/completions"
MODEL_NAME = "Qwen/Qwen3.5-9B"
LISTEN_PORT = 5050
PREFILL_TIMEOUT = 0.2

# --- CONVERSATION STATE ---
history = list(SEED_HISTORY)
cancel_generation = threading.Event()

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

def send_to_mouth(text):
    """Fire-and-forget POST to mouth daemon. Errors silently swallowed."""
    def _post():
        try:
            requests.post(f"{MOUTH_URL}/speak", json={"text": text}, timeout=0.5)
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()

def ask_brain(text):
    cancel_generation.clear()
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
                "stop": ["User:", "Nexus:", "System:", "\n\n"],
                "stream": True
            },
            stream=True,
            timeout=60
        )

        if response.status_code != 200:
            print(f"\nBrain Error {response.status_code}: {response.text}")
            history.pop()
            return

        sentence_buffer = ''
        print("Nexus Engine: ", end="", flush=True)
        for line in response.iter_lines():
            if cancel_generation.is_set():
                response.close()
                break
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
                            sentence_buffer += content
                            if re.search(r'[.!?]["\')\]]?\s', sentence_buffer):
                                send_to_mouth(sentence_buffer.strip())
                                sentence_buffer = ''
                    except json.JSONDecodeError:
                        continue
        if sentence_buffer.strip():
            send_to_mouth(sentence_buffer.strip())
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"\n\033[90m[LLM TTFT: {ttft:.0f}ms | total: {elapsed:.0f}ms]\033[0m\n" if ttft else "\n")

        reply = ''.join(reply_parts).strip()
        if cancel_generation.is_set():
            cancel_generation.clear()
            if reply and len(reply) >= 10 and not any(p in reply.lower() for p in DODGE_PHRASES):
                history.append(('Nexus', reply))
            else:
                history.pop()
        elif reply and len(reply) >= 10 and not any(p in reply.lower() for p in DODGE_PHRASES):
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

        elif self.path == '/stream':
            self.send_response(200)
            self.end_headers()
            text = body.get('text', '')
            if text:
                print(f'\r> {text}    ', end='', flush=True)

        elif self.path == '/flush':
            self.send_response(200)
            self.end_headers()
            text = body.get('text', '')
            asr_ttft = body.get('asr_ttft')
            speech_elapsed = body.get('speech_elapsed')
            if text:
                print(f'\r> {text}    ')
            if asr_ttft is not None and speech_elapsed is not None:
                print(f'\033[90m[ASR TTFT: {asr_ttft:.0f}ms | speech: {speech_elapsed:.0f}ms]\033[0m')
            if text and re.match(r'^nexus[,.]?\s*clear\s+memory[.!?]*$', text.lower().strip()):
                history.clear()
                history.extend(SEED_HISTORY)
                print('\033[92m[Memory cleared — history reset]\033[0m')
                print('Listening...', end='', flush=True)
            elif text:
                if is_report_request(text):
                    history.append(('User', text))
                    print('\n\033[96m[Report pipeline]\033[0m')
                    result = run_report_pipeline(text)
                    jid = result.get('job_id', '')
                    link = result.get('tableau_link', '')
                    ok = result.get('ok')
                    print(
                        f"\033[96mjob_id={jid} tableau_link={link} "
                        f"rows={result.get('row_count')} ok={ok}\033[0m"
                    )
                    summary = (result.get('summary') or '').strip()
                    if summary:
                        print(f"Nexus (report): {summary}\n")
                        history.append(('Nexus', summary))
                        out_path = write_spoken_report_output(
                            jid,
                            summary,
                            tableau_link=link or "",
                            ok=bool(ok),
                            row_count=int(result.get('row_count') or 0),
                            error=result.get('error'),
                        )
                        print(f"\033[92m[Report summary written to {out_path} — not sent to mouth]\033[0m\n")
                    else:
                        history.pop()
                else:
                    ask_brain(text)
                print('Listening...', end='', flush=True)

        elif self.path == '/stop':
            self.send_response(200)
            self.end_headers()
            cancel_generation.set()

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
    print('Listening...', end='', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nNexus engine shutting down...')
        server.server_close()

if __name__ == '__main__':
    main()
