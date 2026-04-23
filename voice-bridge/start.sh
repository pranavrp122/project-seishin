#!/usr/bin/env bash
# Start the voice bridge. Loads .env from project root or ~/.sei/.env
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load env
SEI_ENV="$HOME/.sei/.env"
if [[ -f "$SEI_ENV" ]]; then
    set -a; source "$SEI_ENV"; set +a
elif [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

exec python3 "$SCRIPT_DIR/voice_bridge.py"
