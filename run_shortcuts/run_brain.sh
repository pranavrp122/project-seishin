#!/bin/bash

# Stop and remove existing brain container if running
docker rm -f seishin-brain 2>/dev/null

docker run -d \
  --name seishin-brain \
  --gpus all \
  -p 8001:8000 \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen3.5-9B \
  --quantization fp8 \
  --enable-prefix-caching \
  --kv-cache-dtype fp8 \
  --gpu-memory-utilization 0.55

echo "seishin-brain started. Monitor with: docker logs seishin-brain -f"
