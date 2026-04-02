#!/bin/bash
# Restart seishin-mouth with GPU + PulseAudio access
# Run from the host WSL2 shell

docker stop seishin-mouth 2>/dev/null
docker rm seishin-mouth 2>/dev/null

docker run -d \
  --name seishin-mouth \
  --gpus all \
  -p 5051:5051 \
  -v /home/prana/nexus-engine/scripts:/workspace/scripts \
  -v /mnt/wslg:/mnt/wslg \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -e PULSE_SERVER=unix:/mnt/wslg/PulseServer \
  -e PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512 \
  pytorch/pytorch:2.11.0-cuda13.0-cudnn9-runtime \
  sleep infinity

echo "Installing deps..."
docker exec seishin-mouth bash -c "apt-get update -qq && apt-get install -y -q libportaudio2 libpulse0 libasound2-plugins sox libsox-dev"

docker exec seishin-mouth bash -c "cat > /etc/asound.conf << 'ASOUND'
pcm.!default { type pulse }
ctl.!default { type pulse }
ASOUND"

docker exec seishin-mouth pip install --quiet --break-system-packages torchaudio==2.11.0 qwen-tts sounddevice scipy requests

echo "seishin-mouth container ready."
echo "First run will download Qwen3-TTS-12Hz-1.7B-CustomVoice (~4.54 GB)."
