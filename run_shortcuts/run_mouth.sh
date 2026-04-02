#!/bin/bash
docker exec -it \
  -e PULSE_SERVER=unix:/mnt/wslg/PulseServer \
  -e TTS_SPEAKER="${TTS_SPEAKER:-Aiden}" \
  seishin-mouth python3 -W ignore /workspace/scripts/mouth_daemon.py
