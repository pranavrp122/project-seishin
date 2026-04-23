#!/usr/bin/env bash
# =============================================================================
# create_instance.sh -- One-time setup: creates key pair, security group,
#                       and g6e.xlarge instance for Gemma 4 FP8 on L40S.
#
# Run once from your PC. Outputs IDs to add to .env.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REGION="${AWS_GPU_REGION:-us-east-1}"
AZ="${AWS_GPU_AZ:-us-east-1b}"
KEY_NAME="seishin-gpu"
SG_NAME="seishin-vllm-sg"
INSTANCE_NAME="seishin-vllm"
INSTANCE_TYPE="g6e.xlarge"
AMI_ID="ami-09d0a18beb02cc7d4"  # Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.7 (Ubuntu 22.04) 20260419

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# Source .env for HF_TOKEN etc
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

MY_IP=$(curl -s https://checkip.amazonaws.com)
info "Your current IP: $MY_IP"

# --- Key pair ---
KEY_FILE="$HOME/.ssh/${KEY_NAME}.pem"
if aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" &>/dev/null; then
    info "Key pair '$KEY_NAME' already exists."
    if [[ ! -f "$KEY_FILE" ]]; then
        warn "Key file not found at $KEY_FILE — you may need to delete and recreate the key pair."
    fi
else
    info "Creating key pair '$KEY_NAME'..."
    aws ec2 create-key-pair \
        --key-name "$KEY_NAME" \
        --region "$REGION" \
        --query 'KeyMaterial' \
        --output text > "$KEY_FILE"
    chmod 400 "$KEY_FILE"
    info "Key saved to $KEY_FILE"
fi

# --- Security group ---
SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SG_NAME" \
    --region "$REGION" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || echo "None")

if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
    info "Creating security group '$SG_NAME'..."
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SG_NAME" \
        --description "Sei Engine vLLM - SSH + vLLM API" \
        --region "$REGION" \
        --query 'GroupId' \
        --output text)
    info "Created SG: $SG_ID"

    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 22 \
        --cidr "${MY_IP}/32" --region "$REGION"
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 8000 \
        --cidr "${MY_IP}/32" --region "$REGION"
    info "SG rules added for $MY_IP (SSH + vLLM port 8000)"
else
    info "Security group '$SG_NAME' already exists: $SG_ID"
fi

# --- EC2 instance ---
INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running,stopped,pending,stopping" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text 2>/dev/null || echo "None")

if [[ "$INSTANCE_ID" == "None" || -z "$INSTANCE_ID" ]]; then
    info "Launching $INSTANCE_TYPE instance..."
    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --placement "AvailabilityZone=${AZ}" \
        --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":120,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]" \
        --region "$REGION" \
        --query 'Instances[0].InstanceId' \
        --output text)
    info "Launched instance: $INSTANCE_ID"

    info "Waiting for instance to be running..."
    aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
else
    info "Instance already exists: $INSTANCE_ID"
fi

PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

info "Instance running at: $PUBLIC_IP"

# --- Print .env additions ---
echo ""
echo "================================================================"
echo "Add these to your .env file:"
echo "================================================================"
echo "AWS_GPU_INSTANCE_ID=${INSTANCE_ID}"
echo "AWS_GPU_SG_ID=${SG_ID}"
echo "AWS_GPU_REGION=${REGION}"
echo "AWS_GPU_KEY=${KEY_FILE}"
echo "================================================================"
echo ""
echo "Then run setup_instance.sh to install vLLM + download the model:"
echo "  bash scripts/aws/setup_instance.sh"
echo ""
info "SSH access: ssh -i $KEY_FILE ubuntu@${PUBLIC_IP}"
