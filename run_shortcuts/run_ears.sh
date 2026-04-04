#!/bin/bash
trap 'docker exec seishin-ears pkill -f ears_daemon.py 2>/dev/null; exit 0' INT
docker exec -it \
  -e PULSE_SERVER=unix:/mnt/wslg/PulseServer \
  -e PYTHONWARNINGS=ignore \
  -e NEMO_TESTING=1 \
  seishin-ears python3 -u -W ignore /workspace/scripts/ears_daemon.py
