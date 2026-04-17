#!/usr/bin/env bash
set -euo pipefail

# Stop the AWS GPU instance to halt compute billing.
# EBS storage (~200 GB gp3) still costs ~$16/mo while stopped.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

INSTANCE_ID="${AWS_GPU_INSTANCE_ID:?Set AWS_GPU_INSTANCE_ID in .env}"
REGION="${AWS_GPU_REGION:-us-east-1}"

echo "Stopping GPU instance $INSTANCE_ID..."
aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION" >/dev/null

echo "Waiting for instance to stop..."
aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID" --region "$REGION"

echo "Instance stopped. \$0/hr compute accruing."
echo "EBS storage (~200 GB gp3) still costs ~\$16/mo."
