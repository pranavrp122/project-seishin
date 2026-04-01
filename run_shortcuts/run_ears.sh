#!/bin/bash
sudo docker start seishin-ears > /dev/null 2>&1 || true
docker exec -it \
  -e PULSE_SERVER=unix:/mnt/wslg/PulseServer \
  -e PYTHONWARNINGS=ignore \
  -e NEMO_TESTING=1 \
  seishin-ears python3 -W ignore /workspace/scripts/ears_daemon.py
