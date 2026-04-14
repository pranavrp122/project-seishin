#!/usr/bin/env bash
# =============================================================================
# compare.sh -- Run both stages and compare VRAM, speed, quality
#
# This is the main test runner. It:
#   1. Runs Stage 1 (NVFP4 + FP8 KV), benchmarks, saves results
#   2. Stops Stage 1
#   3. Runs Stage 2 (NVFP4 + TQ KV), benchmarks, saves results
#   4. Prints side-by-side comparison
#
# Usage:
#   ./compare.sh           -- Run both stages
#   ./compare.sh report    -- Just print comparison from saved results
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

info()   { echo -e "${GREEN}[INFO]${NC} $*"; }
header() { echo -e "\n${CYAN}=== $* ===${NC}"; }

mkdir -p "$RESULTS_DIR"

run_stage() {
    local stage="$1"   # baseline or tq
    local label="$2"
    local output="$RESULTS_DIR/${stage}.json"

    header "Running $label"

    # Start server
    "$SCRIPT_DIR/run.sh" "$stage"

    # Run benchmarks
    info "Running benchmarks..."
    "$SCRIPT_DIR/benchmark.sh" --runs 3 --output "$output"

    # Run quality tests and capture output
    info "Running quality tests..."
    "$SCRIPT_DIR/test.sh" quality 2>&1 | tee "$RESULTS_DIR/${stage}-quality.txt"

    # Record final VRAM
    nvidia-smi --query-gpu=memory.used --format=csv,noheader > "$RESULTS_DIR/${stage}-vram.txt"

    # Stop server
    "$SCRIPT_DIR/run.sh" stop

    # Wait for GPU memory to settle
    sleep 5
    info "$label complete. Results in $output"
}

print_report() {
    header "Comparison Report"

    python3 << 'PYEOF'
import json
import os

results_dir = os.environ.get("RESULTS_DIR", "results")

stages = {}
for stage in ["baseline", "tq"]:
    path = os.path.join(results_dir, f"{stage}.json")
    if os.path.exists(path):
        with open(path) as f:
            stages[stage] = json.load(f)

if not stages:
    print("No results found. Run: ./compare.sh")
    exit(0)

labels = {
    "baseline": "NVFP4 + FP8 KV",
    "tq": "NVFP4 + TQ k8v4"
}

# VRAM comparison
print("\n--- VRAM Usage ---")
print(f"{'Stage':<22} {'Idle':<15} {'Under Load':<15}")
print("-" * 52)
for stage, data in stages.items():
    vram_file = os.path.join(results_dir, f"{stage}-vram.txt")
    vram_load = open(vram_file).read().strip() if os.path.exists(vram_file) else "?"
    print(f"{labels.get(stage, stage):<22} {data.get('vram_idle', '?'):<15} {vram_load:<15}")

# Throughput comparison
print("\n--- Throughput ---")
print(f"{'Test':<20} ", end="")
for stage in stages:
    print(f"{labels.get(stage, stage):<25} ", end="")
print()
print("-" * (20 + 25 * len(stages)))

for test_name in ["Short (50 tok)", "Medium (200 tok)", "Long (500 tok)"]:
    print(f"{test_name:<20} ", end="")
    for stage, data in stages.items():
        benchmarks = data.get("benchmarks", {})
        if test_name in benchmarks:
            b = benchmarks[test_name]
            ttft = b.get("avg_ttft_ms", "?")
            tps = b.get("avg_tok_per_sec", "?")
            print(f"TTFT:{ttft}ms tok/s:{tps:<8} ", end="")
        else:
            print(f"{'N/A':<25} ", end="")
    print()

# Delta calculation if both stages present
if "baseline" in stages and "tq" in stages:
    print("\n--- Delta (TQ vs Baseline) ---")
    for test_name in ["Short (50 tok)", "Medium (200 tok)", "Long (500 tok)"]:
        b_base = stages["baseline"].get("benchmarks", {}).get(test_name, {})
        b_tq = stages["tq"].get("benchmarks", {}).get(test_name, {})
        if b_base and b_tq:
            try:
                ttft_delta = b_tq["avg_ttft_ms"] - b_base["avg_ttft_ms"]
                tps_delta_pct = ((b_tq["avg_tok_per_sec"] - b_base["avg_tok_per_sec"])
                                 / b_base["avg_tok_per_sec"] * 100)
                print(f"  {test_name}: TTFT {ttft_delta:+.1f}ms, tok/s {tps_delta_pct:+.1f}%")
            except (TypeError, ZeroDivisionError):
                print(f"  {test_name}: could not compute delta")

# Quality comparison
print("\n--- Quality ---")
for stage in stages:
    quality_file = os.path.join(results_dir, f"{stage}-quality.txt")
    if os.path.exists(quality_file):
        with open(quality_file) as f:
            lines = f.readlines()
        # Find the results line
        for line in lines:
            if "results:" in line.lower() and "passed" in line.lower():
                print(f"  {labels.get(stage, stage)}: {line.strip()}")
                break

print()
PYEOF
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
CMD="${1:-run}"
export RESULTS_DIR

case "$CMD" in
    run)
        run_stage "baseline" "Stage 1: NVFP4 + FP8 KV (baseline)"
        run_stage "tq" "Stage 2: NVFP4 + TurboQuant KV"
        print_report
        ;;
    report)
        print_report
        ;;
    *)
        echo "Usage: $0 [run|report]"
        ;;
esac
