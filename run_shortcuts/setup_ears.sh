#!/bin/bash
# Build ears image and create container
# Usage: bash run_shortcuts/setup_ears.sh

set -euo pipefail

IMAGE="seishin-ears:latest"
CONTAINER="seishin-ears"

echo "Building ears image..."
docker build -f docker/Dockerfile.ears -t "$IMAGE" ~/project-seishin/docker/

# Remove old container if exists
docker rm -f "$CONTAINER" 2>/dev/null || true

echo "Creating container..."
docker run -d \
  --name "$CONTAINER" \
  --gpus all \
  --ipc=host \
  --privileged \
  -v /home/prana/nexus-engine/scripts:/workspace/scripts \
  -v /mnt/wslg:/mnt/wslg \
  -v /run/user/1000/pulse:/run/user/1000/pulse \
  -v /home/prana/.cache/torch:/root/.cache/torch \
  -v /home/prana/.cache/huggingface:/root/.cache/huggingface \
  -e PYTORCH_ALLOC_CONF=max_split_size_mb:256 \
  "$IMAGE" \
  sleep infinity

echo "Container ready. Start daemon with: bash run_shortcuts/run_ears.sh"
