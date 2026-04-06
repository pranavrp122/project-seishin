#!/bin/bash
# Restart seishin-ears with full audio + GPU access
# Run from the host WSL2 shell

docker stop seishin-ears 2>/dev/null
docker rm seishin-ears 2>/dev/null

docker run -d \
  --name seishin-ears \
  --gpus all \
  --device /dev/snd \
  -v /home/prana/nexus-engine/scripts:/workspace/scripts \
  -v /mnt/wslg:/mnt/wslg \
  -v /run/user/1000/pulse:/run/user/1000/pulse \
  -v ~/.cache/torch:/root/.cache/torch \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -e PULSE_SERVER=unix:/mnt/wslg/PulseServer \
  -e PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:256 \
  -e XDG_RUNTIME_DIR=/run/user/1000 \
  nvcr.io/nvidia/nemo:26.02 \
  sleep infinity

echo "Installing deps..."
docker exec seishin-ears apt-get install -y -q libportaudio2 libpulse0 libasound2-plugins

docker exec seishin-ears bash -c "cat > /etc/asound.conf << 'EOF'
pcm.!default { type pulse }
ctl.!default { type pulse }
EOF"

docker exec seishin-ears pip install --quiet sounddevice requests onnxruntime

echo "seishin-ears ready. Run the engine with:"
echo "  docker exec -it -e PULSE_SERVER=unix:/mnt/wslg/PulseServer seishin-ears python3 /workspace/scripts/nexus_engine.py"
