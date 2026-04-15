#!/usr/bin/env python3
"""Stress test: multi-turn conversation with large system prompt.

Measures TTFT, tokens/sec, and quality across growing context.
"""
import json
import time
import sys
import urllib.request

API = "http://localhost:8000/v1/chat/completions"
MODEL = "gemma-4"

with open("/tmp/test_guide.txt") as f:
    GUIDE = f.read()

TURNS = [
    "Hey, I just got home from work. Long day but nothing too crazy.",
    "Actually you know what, my coworker said something kind of hurtful today. She told me my presentation was 'fine' in a way that clearly meant it wasn't.",
    "I don't know, maybe I'm overreacting. She's usually nice. But the way she said it in front of everyone...",
    "You're right. I think what bothers me most is that I spent two weeks on that presentation. I really tried.",
    "Thanks. Hey, switching gears - I've been thinking about learning guitar. Do you think that's a good idea for stress relief?",
    "Ha, you're right. I used to play piano as a kid actually. Maybe I should pick that back up instead.",
    "Yeah... my mom taught me. She passed away three years ago. Playing piano feels complicated now.",
    "Thank you for saying that. I think she'd want me to play again. Maybe I'll dust off the keyboard this weekend.",
]


def call_api(messages, stream=True):
    """Call the API and measure TTFT + generation speed."""
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "max_tokens": 150,
        "temperature": 0.8,
        "stream": stream,
    }).encode()

    req = urllib.request.Request(
        API,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    t_start = time.perf_counter()
    ttft = None
    chunks = []
    total_tokens = 0
    content = ""

    if stream:
        with urllib.request.urlopen(req) as resp:
            for raw_line in resp:
                line = raw_line.decode().strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = chunk["choices"][0].get("delta", {})
                tok = delta.get("content", "")
                if tok and ttft is None:
                    ttft = (time.perf_counter() - t_start) * 1000  # ms
                if tok:
                    content += tok
                    total_tokens += 1
    else:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
        content = body["choices"][0]["message"]["content"]
        total_tokens = body["usage"]["completion_tokens"]
        ttft = (time.perf_counter() - t_start) * 1000

    t_total = time.perf_counter() - t_start
    gen_time = t_total - (ttft / 1000 if ttft else 0)
    tps = total_tokens / gen_time if gen_time > 0 else 0

    return {
        "content": content,
        "ttft_ms": ttft,
        "total_time_s": t_total,
        "tokens": total_tokens,
        "tps": tps,
    }


def estimate_tokens(text):
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def main():
    messages = [{"role": "system", "content": GUIDE}]
    guide_tokens = estimate_tokens(GUIDE)

    print(f"System prompt: {len(GUIDE):,} bytes (~{guide_tokens:,} tokens)")
    print(f"Running {len(TURNS)} conversation turns...\n")
    print(f"{'Turn':<5} {'Context':>8} {'TTFT':>10} {'Tok/s':>8} {'Tokens':>7}  Response")
    print("-" * 100)

    for i, user_msg in enumerate(TURNS, 1):
        messages.append({"role": "user", "content": user_msg})
        ctx_tokens = sum(estimate_tokens(m["content"]) for m in messages)

        result = call_api(messages)

        messages.append({"role": "assistant", "content": result["content"]})

        # Truncate response for display
        preview = result["content"][:80].replace("\n", " ")
        if len(result["content"]) > 80:
            preview += "..."

        print(
            f"{i:<5} {ctx_tokens:>7}t "
            f"{result['ttft_ms']:>8.0f}ms "
            f"{result['tps']:>7.1f} "
            f"{result['tokens']:>6}  "
            f"{preview}"
        )

    print("-" * 100)
    total_ctx = sum(estimate_tokens(m["content"]) for m in messages)
    print(f"\nFinal context size: ~{total_ctx:,} tokens")
    print(f"System prompt: ~{guide_tokens:,} tokens ({len(GUIDE)/1024:.1f} KB)")
    print(f"Conversation: ~{total_ctx - guide_tokens:,} tokens ({len(TURNS)} turns)")


if __name__ == "__main__":
    main()
