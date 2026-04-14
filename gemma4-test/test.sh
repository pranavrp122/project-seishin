#!/usr/bin/env bash
# =============================================================================
# test.sh -- Test inference and measure VRAM for Gemma 4 26B-A4B
#
# Usage:
#   ./test.sh quick       -- Single short request, verify output is coherent
#   ./test.sh vram        -- Show VRAM usage
#   ./test.sh quality     -- Run quality test prompts (factual, reasoning, code)
#   ./test.sh context     -- Test at various context lengths
#   ./test.sh metrics     -- Dump vLLM Prometheus metrics
#   ./test.sh all         -- Run quick + vram + quality
# =============================================================================
set -euo pipefail

PORT="${VLLM_PORT:-8000}"
MODEL="gemma-4"
API="http://localhost:$PORT/v1"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
header() { echo -e "\n${CYAN}=== $* ===${NC}"; }

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
check_server() {
    if ! curl -sf "http://localhost:$PORT/health" &>/dev/null; then
        error "Server not responding at localhost:$PORT"
        error "Start it with: ./run.sh baseline"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Chat completion helper
# ---------------------------------------------------------------------------
chat() {
    local prompt="$1"
    local max_tokens="${2:-200}"
    local temp="${3:-0.7}"

    curl -sf "$API/chat/completions" \
        -H "Content-Type: application/json" \
        -d "$(cat <<EOF
{
    "model": "$MODEL",
    "messages": [{"role": "user", "content": "$prompt"}],
    "max_tokens": $max_tokens,
    "temperature": $temp
}
EOF
)"
}

# Extract just the text content from a chat response
chat_text() {
    chat "$@" | python3 -c "
import sys, json
resp = json.load(sys.stdin)
if 'choices' in resp and len(resp['choices']) > 0:
    print(resp['choices'][0]['message']['content'])
    usage = resp.get('usage', {})
    print(f'\n--- tokens: prompt={usage.get(\"prompt_tokens\",\"?\")}, completion={usage.get(\"completion_tokens\",\"?\")}, total={usage.get(\"total_tokens\",\"?\")}', file=sys.stderr)
else:
    print('ERROR: No response', file=sys.stderr)
    print(json.dumps(resp, indent=2), file=sys.stderr)
"
}

# ---------------------------------------------------------------------------
# Quick sanity check
# ---------------------------------------------------------------------------
test_quick() {
    header "Quick Sanity Check"
    info "Sending a simple prompt..."
    echo ""

    local response
    response=$(chat_text "Hello! Tell me a short joke about programming." 150 0.7)
    echo "$response"
    echo ""

    # Basic coherence check: response should have >20 chars and no NaN/garbage
    if [[ ${#response} -lt 20 ]]; then
        error "Response too short (${#response} chars). Possible issue."
        return 1
    fi
    if echo "$response" | grep -qi "nan\|<0x\|\\\\x[0-9a-f]"; then
        error "Response contains NaN or garbage bytes!"
        error "Check: is VLLM_NVFP4_GEMM_BACKEND=marlin set?"
        error "Check: is --moe-backend marlin set?"
        return 1
    fi

    info "Response looks coherent (${#response} chars)."
}

# ---------------------------------------------------------------------------
# VRAM measurement
# ---------------------------------------------------------------------------
test_vram() {
    header "VRAM Usage"

    info "GPU memory:"
    nvidia-smi --query-gpu=name,memory.used,memory.total,memory.free,utilization.gpu --format=csv,noheader
    echo ""

    info "Detailed GPU memory breakdown:"
    nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv,noheader 2>/dev/null || true
    echo ""

    # Get vLLM metrics if available
    local metrics
    if metrics=$(curl -sf "http://localhost:$PORT/metrics" 2>/dev/null); then
        info "vLLM KV cache metrics:"
        echo "$metrics" | grep -E "vllm:gpu_cache_usage_perc|vllm:num_gpu_blocks|vllm:kv_cache" | head -10
        echo ""

        info "vLLM model metrics:"
        echo "$metrics" | grep -E "vllm:num_requests|vllm:model_forward" | head -5
    fi
}

# ---------------------------------------------------------------------------
# Quality tests
# ---------------------------------------------------------------------------
test_quality() {
    header "Quality Tests"
    local pass=0
    local fail=0

    # Test 1: Factual knowledge
    info "Test 1/5: Factual knowledge"
    local r1
    r1=$(chat_text "What is the capital of France? Answer in one word." 10 0.0)
    echo "  Response: $r1"
    if echo "$r1" | grep -qi "paris"; then
        info "  PASS"; ((pass++))
    else
        warn "  FAIL (expected 'Paris')"; ((fail++))
    fi

    # Test 2: Math
    info "Test 2/5: Basic math"
    local r2
    r2=$(chat_text "What is 7 * 8? Just give the number." 10 0.0)
    echo "  Response: $r2"
    if echo "$r2" | grep -q "56"; then
        info "  PASS"; ((pass++))
    else
        warn "  FAIL (expected '56')"; ((fail++))
    fi

    # Test 3: Reasoning
    info "Test 3/5: Reasoning"
    local r3
    r3=$(chat_text "If all roses are flowers, and some flowers fade quickly, can we conclude that some roses fade quickly? Answer yes or no and explain briefly." 150 0.0)
    echo "  Response: $r3"
    if echo "$r3" | grep -qi "no\|cannot\|not necessarily"; then
        info "  PASS"; ((pass++))
    else
        warn "  FAIL (expected 'no/cannot conclude')"; ((fail++))
    fi

    # Test 4: Code generation
    info "Test 4/5: Code generation"
    local r4
    r4=$(chat_text "Write a Python function that returns the factorial of a number n. Just the function, no explanation." 200 0.0)
    echo "  Response: $r4"
    if echo "$r4" | grep -q "def.*factorial\|def.*fact"; then
        info "  PASS"; ((pass++))
    else
        warn "  FAIL (expected function definition)"; ((fail++))
    fi

    # Test 5: Longer generation coherence
    info "Test 5/5: Longer generation (coherence check)"
    local r5
    r5=$(chat_text "Explain how a CPU processes instructions, in about 100 words." 200 0.7)
    echo "  Response: $r5"
    local r5_len=${#r5}
    if [[ $r5_len -gt 100 ]]; then
        info "  PASS ($r5_len chars)"; ((pass++))
    else
        warn "  FAIL (response too short: $r5_len chars)"; ((fail++))
    fi

    echo ""
    info "Quality results: $pass/5 passed, $fail/5 failed"
    if [[ $fail -gt 1 ]]; then
        warn "Multiple quality failures. Check model loading and quantization."
    fi
}

# ---------------------------------------------------------------------------
# Context length test
# ---------------------------------------------------------------------------
test_context() {
    header "Context Length Test"
    info "Testing at various input sizes to measure VRAM scaling."
    info "This only matters for the 5 global attention layers."
    echo ""

    # Baseline VRAM
    info "Baseline (idle):"
    nvidia-smi --query-gpu=memory.used --format=csv,noheader
    echo ""

    for tokens in 100 1000 4000 8000 16000; do
        # Generate a prompt of approximately $tokens input tokens
        # (~4 chars per token is a rough estimate)
        local chars=$((tokens * 4))
        local filler
        filler=$(python3 -c "print('The quick brown fox jumps over the lazy dog. ' * ($chars // 46 + 1))")
        filler="${filler:0:$chars}"

        info "Testing ~${tokens} input tokens..."
        local start_time
        start_time=$(date +%s%N)

        local response
        response=$(chat "$filler Summarize the above in one sentence." 50 0.0 2>/dev/null)

        local end_time
        end_time=$(date +%s%N)
        local elapsed_ms=$(( (end_time - start_time) / 1000000 ))

        # Check for errors
        local error_msg
        error_msg=$(echo "$response" | python3 -c "
import sys, json
r = json.load(sys.stdin)
if 'error' in r:
    print(r['error'].get('message', str(r['error'])))
elif 'choices' not in r:
    print('No choices in response')
" 2>/dev/null || true)

        if [[ -n "$error_msg" ]]; then
            warn "  ${tokens} tokens: ERROR - $error_msg"
        else
            local completion_tokens
            completion_tokens=$(echo "$response" | python3 -c "
import sys, json
r = json.load(sys.stdin)
print(r.get('usage', {}).get('completion_tokens', '?'))
" 2>/dev/null || echo "?")
            local vram
            vram=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader)
            info "  ${tokens} tokens: ${elapsed_ms}ms TTFT+gen, ${completion_tokens} output tokens, VRAM: $vram"
        fi
    done
}

# ---------------------------------------------------------------------------
# Raw metrics dump
# ---------------------------------------------------------------------------
test_metrics() {
    header "vLLM Metrics"
    curl -sf "http://localhost:$PORT/metrics" | grep -E "^vllm:" | sort
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
usage() {
    echo "Usage: $0 [quick|vram|quality|context|metrics|all]"
    echo ""
    echo "Commands:"
    echo "  quick     Single request sanity check (default)"
    echo "  vram      Show VRAM usage"
    echo "  quality   Run quality test prompts"
    echo "  context   Test at various context lengths"
    echo "  metrics   Dump vLLM Prometheus metrics"
    echo "  all       Run quick + vram + quality"
}

CMD="${1:-quick}"
check_server

case "$CMD" in
    quick)   test_quick ;;
    vram)    test_vram ;;
    quality) test_quality ;;
    context) test_context ;;
    metrics) test_metrics ;;
    all)     test_quick; test_vram; test_quality ;;
    -h|--help) usage ;;
    *) error "Unknown command: $CMD"; usage; exit 1 ;;
esac
