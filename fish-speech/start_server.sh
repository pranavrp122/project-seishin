#!/bin/bash
export LD_LIBRARY_PATH="/home/prana/fish-speech/.venv/lib/python3.11/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH}"
exec /home/prana/fish-speech/.venv/bin/python3 tools/api_server.py "$@"
