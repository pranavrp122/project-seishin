#!/bin/bash
# NOTE: start seishin-mouth in a separate terminal: bash run_shortcuts/run_mouth.sh
docker exec -it \
  -e PULSE_SERVER=unix:/mnt/wslg/PulseServer \
  -e PYTHONWARNINGS=ignore \
  -e NEMO_TESTING=1 \
  seishin-ears python3 -W ignore /workspace/scripts/nexus_engine.py
