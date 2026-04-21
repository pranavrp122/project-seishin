#!/usr/bin/env bash
# Run sei_engine locally (text-only mode, no TTS/ASR)
# Usage: bash scripts/start_sei.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."
VENV="$PROJECT_ROOT/.sei_venv"

# Load .env — strip Windows CRLF line endings before sourcing
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  source <(sed 's/\r//' "$PROJECT_ROOT/.env")
  set +a
fi

# Defaults for local dev
export SEI_DEV_MODE="${SEI_DEV_MODE:-1}"
export SEI_LLM_URL="${SEI_LLM_URL:-http://<SERVER_IP>:8000}"
export GMAIL_CLIENT_SECRETS="${GMAIL_CLIENT_SECRETS:-$HOME/.sei/gmail_credentials.json}"

source "$VENV/bin/activate"
cd "$SCRIPT_DIR"

echo "Starting sei_engine..."
echo "LLM: $SEI_LLM_URL"
echo "Port: 5052"
python3 -u sei_engine.py
