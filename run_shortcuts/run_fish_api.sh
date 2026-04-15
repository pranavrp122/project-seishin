#!/bin/bash
# Fish Speech API server — HTTP streaming TTS on port 8080
#
# This replaces mouth_daemon for remote TTS. Do NOT run both simultaneously
# (mutual exclusivity — both load the Fish Speech model onto GPU).
#
# Prerequisites: Same as run_mouth.sh (fish-speech-server docker image)

docker exec -it \
  -e TTS_REFERENCE_ID="${TTS_REFERENCE_ID:-archie}" \
  -e COMPILE="${COMPILE:-1}" \
  -w /workspace \
  seishin-mouth \
  uv run python tools/api_server.py \
    --listen 127.0.0.1:8080 \
    --compile \
    --half
