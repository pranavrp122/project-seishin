#!/usr/bin/env bash
# =============================================================================
# benchmark.sh -- Measure TTFT, tok/s, and VRAM for Gemma 4 26B-A4B
#
# Usage:
#   ./benchmark.sh              -- Run full benchmark suite
#   ./benchmark.sh --runs 5     -- Set number of runs per test (default: 3)
#   ./benchmark.sh --output results.json  -- Save results to file
#
# Requires: python3, curl
# =============================================================================
set -euo pipefail

PORT="${VLLM_PORT:-8000}"
MODEL="gemma-4"
API="http://localhost:$PORT/v1"
RUNS=3
OUTPUT=""

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

info()   { echo -e "${GREEN}[INFO]${NC} $*"; }
header() { echo -e "\n${CYAN}=== $* ===${NC}"; }

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --runs)   RUNS="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        *)        echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# Check server
if ! curl -sf "http://localhost:$PORT/health" &>/dev/null; then
    echo "Server not responding at localhost:$PORT"
    echo "Start it with: ./run.sh baseline"
    exit 1
fi

# ---------------------------------------------------------------------------
# Benchmark using streaming to get accurate TTFT
# ---------------------------------------------------------------------------
BENCHMARK_SCRIPT=$(cat << 'PYEOF'
import sys
import json
import time
import urllib.request

API = sys.argv[1]
MODEL = sys.argv[2]
PROMPT = sys.argv[3]
MAX_TOKENS = int(sys.argv[4])
RUNS = int(sys.argv[5])

results = []

for run in range(RUNS):
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
        "stream": True
    }).encode()

    req = urllib.request.Request(
        f"{API}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    start = time.perf_counter()
    first_token_time = None
    tokens = 0
    full_text = []

    with urllib.request.urlopen(req) as resp:
        buffer = ""
        for chunk in iter(lambda: resp.read(1024).decode("utf-8", errors="replace"), ""):
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                try:
                    data = json.loads(line[6:])
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        tokens += 1
                        full_text.append(content)
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass

    end = time.perf_counter()

    ttft_ms = (first_token_time - start) * 1000 if first_token_time else None
    total_s = end - start
    decode_s = (end - first_token_time) if first_token_time else total_s
    tps = (tokens - 1) / decode_s if tokens > 1 and decode_s > 0 else 0

    result = {
        "run": run + 1,
        "ttft_ms": round(ttft_ms, 1) if ttft_ms else None,
        "total_s": round(total_s, 2),
        "tokens": tokens,
        "tok_per_sec": round(tps, 1),
        "text_preview": "".join(full_text)[:80]
    }
    results.append(result)

    # Print per-run result
    print(f"  Run {run+1}: TTFT={result['ttft_ms']}ms, "
          f"tokens={tokens}, "
          f"tok/s={result['tok_per_sec']}, "
          f"total={result['total_s']}s",
          file=sys.stderr)

# Compute averages
avg_ttft = sum(r["ttft_ms"] for r in results if r["ttft_ms"]) / len([r for r in results if r["ttft_ms"]]) if results else 0
avg_tps = sum(r["tok_per_sec"] for r in results) / len(results) if results else 0
avg_tokens = sum(r["tokens"] for r in results) / len(results) if results else 0

summary = {
    "avg_ttft_ms": round(avg_ttft, 1),
    "avg_tok_per_sec": round(avg_tps, 1),
    "avg_tokens": round(avg_tokens, 1),
    "runs": results
}
print(json.dumps(summary))
PYEOF
)

run_bench() {
    local label="$1"
    local prompt="$2"
    local max_tokens="$3"

    info "$label ($RUNS runs, max_tokens=$max_tokens)"

    local result
    result=$(python3 -c "$BENCHMARK_SCRIPT" "$API" "$MODEL" "$prompt" "$max_tokens" "$RUNS" 2>&1)

    # stderr lines are per-run results, stdout is JSON summary
    echo "$result" | grep -v "^{" || true
    local json_line
    json_line=$(echo "$result" | grep "^{" | tail -1)
    echo "  Average: TTFT=$(echo "$json_line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d[\"avg_ttft_ms\"]}ms')")  tok/s=$(echo "$json_line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['avg_tok_per_sec'])")"
    echo ""

    # Return JSON for aggregation
    echo "$json_line"
}

# ---------------------------------------------------------------------------
# Main benchmark suite
# ---------------------------------------------------------------------------
header "Gemma 4 26B-A4B NVFP4 Benchmark"
info "Server: localhost:$PORT"
info "Runs per test: $RUNS"
echo ""

# Record VRAM before benchmarks
VRAM_IDLE=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader | tr -d ' ')
info "VRAM (idle): $VRAM_IDLE"
echo ""

# Warmup (first request has CUDA graph compilation overhead)
header "Warmup"
info "First request (CUDA graph warmup, expect 10-30s)..."
curl -sf "$API/chat/completions" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Hi\"}],\"max_tokens\":5,\"temperature\":0}" \
    > /dev/null
info "Warmup done."

# Benchmark 1: Short generation (TTFT-focused)
header "Benchmark 1: Short Generation (TTFT focus)"
B1=$(run_bench "Short prompt -> 50 tokens" \
    "What is the speed of light?" 50)

# Benchmark 2: Medium generation
header "Benchmark 2: Medium Generation"
B2=$(run_bench "Medium prompt -> 200 tokens" \
    "Explain the theory of relativity in simple terms." 200)

# Benchmark 3: Long generation (throughput-focused)
header "Benchmark 3: Long Generation (throughput focus)"
B3=$(run_bench "Long generation -> 500 tokens" \
    "Write a detailed essay about the history of computing, from Charles Babbage to modern AI." 500)

# VRAM after benchmarks
VRAM_AFTER=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader | tr -d ' ')

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
header "Summary"
echo ""
echo "VRAM idle:  $VRAM_IDLE"
echo "VRAM after: $VRAM_AFTER"
echo ""

# Parse results for summary table
python3 << PYEOF
import json

results = {}
for label, json_str in [
    ("Short (50 tok)", '''$(echo "$B1" | grep "^{" | tail -1)'''),
    ("Medium (200 tok)", '''$(echo "$B2" | grep "^{" | tail -1)'''),
    ("Long (500 tok)", '''$(echo "$B3" | grep "^{" | tail -1)'''),
]:
    try:
        data = json.loads(json_str)
        results[label] = data
    except:
        results[label] = {"avg_ttft_ms": "?", "avg_tok_per_sec": "?", "avg_tokens": "?"}

print(f"{'Test':<20} {'TTFT (ms)':<12} {'tok/s':<10} {'Tokens':<10}")
print("-" * 52)
for label, data in results.items():
    print(f"{label:<20} {data['avg_ttft_ms']:<12} {data['avg_tok_per_sec']:<10} {data['avg_tokens']:<10}")

# Save if output file specified
output_file = "$OUTPUT"
if output_file:
    full_results = {
        "model": "$MODEL",
        "vram_idle": "$VRAM_IDLE",
        "vram_after": "$VRAM_AFTER",
        "runs_per_test": $RUNS,
        "benchmarks": results
    }
    with open(output_file, "w") as f:
        json.dump(full_results, f, indent=2)
    print(f"\nResults saved to {output_file}")
PYEOF
