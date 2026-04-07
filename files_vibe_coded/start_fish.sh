#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Project Seishin — Phase 1
# Fish Audio S2-Pro local inference server
#
# Prereqs:
#   pip install fish-speech
#   or clone: https://github.com/fishaudio/fish-speech
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

FISH_PORT=8080
CHECKPOINT_PATH="checkpoints/fish-speech-1.5"  # adjust to your local path
DEVICE="cuda"

echo "═══════════════════════════════════════════════"
echo "  Project Seishin — Fish Audio TTS Server"
echo "  Port: $FISH_PORT"
echo "  Checkpoint: $CHECKPOINT_PATH"
echo "═══════════════════════════════════════════════"

# Compile with torch.compile for max throughput (Blackwell)
export FISH_COMPILE=1
export TORCH_COMPILE_BACKEND="inductor"

python -m fish_speech.webui.launch \
  --llama-checkpoint-path "$CHECKPOINT_PATH/codec" \
  --decoder-checkpoint-path "$CHECKPOINT_PATH/firefly" \
  --half \
  --compile \
  --port "$FISH_PORT" \
  2>&1 | tee logs/fish_audio.log
