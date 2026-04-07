#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Project Seishin — Phase 1 Master Launcher
# Starts: vLLM → Fish Audio → Pipeline → Dashboard
# ─────────────────────────────────────────────────────────────────

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
log() { echo -e "${CYAN}[seishin]${NC} $*"; }
ok()  { echo -e "${GREEN}[  ok  ]${NC} $*"; }
err() { echo -e "${RED}[ fail ]${NC} $*"; }

# ── Load env (this folder or repo root) ──────
ENV_FILE=""
if [ -f "$ROOT/.env" ]; then
  ENV_FILE="$ROOT/.env"
elif [ -f "$ROOT/../.env" ]; then
  ENV_FILE="$ROOT/../.env"
fi
if [ -n "$ENV_FILE" ]; then
  set -a; source "$ENV_FILE"; set +a
  ok "Loaded .env ($ENV_FILE)"
else
  err ".env not found — copy files_vibe_coded/.env.example to .env here or repo root"
  exit 1
fi

wait_for_port() {
  local name=$1 port=$2 timeout=${3:-60}
  log "Waiting for $name on port $port..."
  for i in $(seq 1 $timeout); do
    if nc -z localhost "$port" 2>/dev/null; then
      ok "$name is up (port $port)"
      return 0
    fi
    sleep 1
  done
  err "$name failed to start on port $port after ${timeout}s"
  exit 1
}

# ── 1. vLLM ──────────────────────────────────
log "Starting vLLM (Qwen 3.5)..."
bash "$ROOT/start_vllm.sh" > "$LOGS/vllm.log" 2>&1 &
VLLM_PID=$!
wait_for_port "vLLM" 8000 120

# ── 2. Fish Audio TTS ─────────────────────────
log "Starting Fish Audio TTS..."
bash "$ROOT/start_fish.sh" > "$LOGS/fish.log" 2>&1 &
FISH_PID=$!
wait_for_port "Fish Audio" 8080 60

# ── 3. Dashboard (static UI) ──────────────────
log "Starting dashboard (HTTP)..."
cd "$ROOT"
python -m http.server 3000 > "$LOGS/dashboard.log" 2>&1 &
DASH_PID=$!
ok "Dashboard available at http://localhost:3000"

# ── 4. Pipeline ───────────────────────────────
log "Starting Seishin pipeline..."
cd "$ROOT"
python pipeline.py > "$LOGS/pipeline.log" 2>&1 &
PIPE_PID=$!

ok "═══════════════════════════════════════════"
ok "  Seishin Phase 1 — All systems running"
ok "  Dashboard:  http://localhost:3000"
ok "  vLLM API:   http://localhost:8000"
ok "  Fish Audio: http://localhost:8080"
ok "  Dashboard WS: ws://localhost:8765"
ok "═══════════════════════════════════════════"

# Trap Ctrl+C to kill all children
cleanup() {
  log "Shutting down..."
  kill $VLLM_PID $FISH_PID $DASH_PID $PIPE_PID 2>/dev/null || true
  ok "All services stopped."
}
trap cleanup EXIT INT TERM

# Tail pipeline log to terminal
tail -f "$LOGS/pipeline.log"
