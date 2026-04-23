#!/usr/bin/env bash
# =============================================================================
# setup_instance.sh -- One-time instance initialization.
#
# Runs from your PC via SSH. Installs vLLM docker image, downloads Gemma 4
# FP8 model, and sets up a systemd service to auto-start vLLM on boot.
#
# Requires AWS_GPU_INSTANCE_ID, AWS_GPU_KEY, HF_TOKEN in .env
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REGION="${AWS_GPU_REGION:-us-east-1}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

INSTANCE_ID="${AWS_GPU_INSTANCE_ID:?Set AWS_GPU_INSTANCE_ID in .env}"
KEY_FILE="${AWS_GPU_KEY:?Set AWS_GPU_KEY in .env}"
HF_TOKEN="${HF_TOKEN:?Set HF_TOKEN in .env}"
VLLM_API_KEY="${SEI_LLM_API_KEY:?Set SEI_LLM_API_KEY in .env}"

PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

[[ -z "$PUBLIC_IP" || "$PUBLIC_IP" == "None" ]] && error "Instance not running or no public IP"
info "Setting up instance at $PUBLIC_IP"

SSH="ssh -i $KEY_FILE -o StrictHostKeyChecking=no ubuntu@${PUBLIC_IP}"

# Upload vllm start script to instance
scp -i "$KEY_FILE" -o StrictHostKeyChecking=no \
    "$SCRIPT_DIR/vllm.sh" \
    "ubuntu@${PUBLIC_IP}:/home/ubuntu/vllm.sh"

# Run setup on instance
$SSH bash <<REMOTE
set -euo pipefail

echo "[INFO] Verifying NVIDIA driver..."
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

echo "[INFO] Verifying Docker + nvidia-container-toolkit..."
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi || {
    echo "[INFO] Installing nvidia-container-toolkit..."
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt-get update -q && sudo apt-get install -y -q nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
}

echo "[INFO] Pulling vLLM image..."
docker pull vllm/vllm-openai:latest

echo "[INFO] Installing huggingface hub..."
pip install --quiet --upgrade huggingface-hub
export PATH="/home/ubuntu/.local/bin:$PATH"

echo "[INFO] Downloading Gemma 4 FP8 model (~26GB)..."
mkdir -p /home/ubuntu/models
hf download RedHatAI/gemma-4-26B-A4B-it-FP8-Dynamic \
    --token ${HF_TOKEN} \
    --local-dir /home/ubuntu/models/gemma4-fp8

echo "[INFO] Saving vLLM API key..."
echo "VLLM_API_KEY=${VLLM_API_KEY}" > /home/ubuntu/.vllm.env
chmod 600 /home/ubuntu/.vllm.env

echo "[INFO] Setting up systemd service..."
chmod +x /home/ubuntu/vllm.sh

sudo tee /etc/systemd/system/vllm-gemma4.service > /dev/null <<SERVICE
[Unit]
Description=vLLM Gemma 4 FP8
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=ubuntu
EnvironmentFile=/home/ubuntu/.vllm.env
ExecStartPre=/usr/bin/docker rm -f vllm-gemma4 || true
ExecStart=/home/ubuntu/vllm.sh
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable vllm-gemma4

echo ""
echo "=== SETUP COMPLETE ==="
echo "Start vLLM:   sudo systemctl start vllm-gemma4"
echo "Check logs:   sudo journalctl -u vllm-gemma4 -f"
echo "Health:       curl http://localhost:8000/health"
REMOTE

info "Instance setup complete."
info "Starting vLLM now..."
$SSH "sudo systemctl start vllm-gemma4"
info "Follow logs: ssh -i $KEY_FILE ubuntu@${PUBLIC_IP} 'sudo journalctl -u vllm-gemma4 -f'"
info "Or run: bash scripts/aws/start_gpu.sh (polls until healthy)"
