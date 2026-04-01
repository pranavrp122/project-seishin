import sys
import time
import json
import requests

BRAIN_URL  = 'http://172.17.0.1:8001/v1/completions'
MODEL_NAME = 'Qwen/Qwen3.5-9B'

# Conversation history: list of (role, text) tuples
# Seeded with the fixed opening exchange so Nexus always starts in character
history = [
    ('User', 'Hello!'),
    ('Nexus', 'Systems online. I am awake and ready.'),
]


def build_prompt() -> str:
    lines = ['The following is a conversation with Nexus, a witty AI.']
    for role, text in history:
        lines.append(f'{role}: {text}')
    lines.append('Nexus:')
    return '\n'.join(lines)


def ask_brain(text: str):
    history.append(('User', text))
    prompt = build_prompt()
    reply_parts = []

    try:
        t0 = time.perf_counter()
        first_token = True
        ttft = None
        response = requests.post(
            BRAIN_URL,
            json={
                'model': MODEL_NAME,
                'prompt': prompt,
                'max_tokens': 300,
                'temperature': 0.7,
                'stop': ['User:', '\n'],
                'stream': True,
            },
            stream=True,
            timeout=60,
        )
        print('\r✨ Nexus: ', end='', flush=True)
        for line in response.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith('data: '):
                    if '[DONE]' in decoded:
                        break
                    data = json.loads(decoded[6:])
                    content = data['choices'][0].get('text', '')
                    if content:
                        if first_token:
                            ttft = (time.perf_counter() - t0) * 1000
                            first_token = False
                        reply_parts.append(content)
                        print(content, end='', flush=True)

        elapsed = (time.perf_counter() - t0) * 1000
        if ttft is not None:
            turn = len([r for r, _ in history if r == 'User'])
            print(f'\n\033[90m[TTFT: {ttft:.0f} ms | total: {elapsed:.0f} ms | turn {turn}]\033[0m')
        print()

        # Store Nexus's reply so it appears in future prompts
        reply = ''.join(reply_parts).strip()
        if reply:
            history.append(('Nexus', reply))

    except requests.exceptions.ConnectionError:
        print(f'\n❌ Cannot reach Brain at {BRAIN_URL} — is seishin-brain running?\n')
        history.pop()  # drop the user turn we just added since it wasn't answered
    except Exception as e:
        print(f'\n❌ Brain error: {e}\n')
        history.pop()


def main():
    print('─' * 50)
    print('  🧠  NEXUS BRAIN TESTER  (with memory)')
    print(f'  Model : {MODEL_NAME}')
    print(f'  URL   : {BRAIN_URL}')
    print('  Type a message and press Enter.')
    print('  Type "reset" to clear conversation history.')
    print('  Ctrl+C or type "exit" to quit.')
    print('─' * 50)

    while True:
        try:
            user_input = input('\nUser: ').strip()
        except (KeyboardInterrupt, EOFError):
            print('\n\n👋 Bye.')
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in ('exit', 'quit', 'q'):
            print('👋 Bye.')
            sys.exit(0)
        if user_input.lower() == 'reset':
            history.clear()
            history.extend([
                ('User', 'Hello!'),
                ('Nexus', 'Systems online. I am awake and ready.'),
            ])
            print('🔄 Conversation history cleared.\n')
            continue

        ask_brain(user_input)


if __name__ == '__main__':
    main()
