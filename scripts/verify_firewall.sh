#!/usr/bin/env bash
# verify_firewall.sh -- Verify services are only reachable via Tailscale
#
# Usage: ./verify_firewall.sh <server-tailscale-ip>
#   Run from the laptop with Tailscale active to verify port exposure.
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <server-tailscale-ip>"
    echo "  Default: <SERVER_IP>"
    exit 1
fi

SERVER_IP="$1"
PASS=0
FAIL=0

echo "=== Service Exposure Verification ==="
echo "Target: $SERVER_IP (Tailscale)"
echo "Date: $(date)"
echo ""

echo "--- Ports that MUST be closed (internal services) ---"
for port in 8000 8001 5050 5051; do
    if nc -z -w 3 "$SERVER_IP" "$port" 2>/dev/null; then
        echo "  FAIL: TCP $port is OPEN (should be closed)"
        FAIL=$((FAIL + 1))
    else
        echo "  PASS: TCP $port is closed"
        PASS=$((PASS + 1))
    fi
done

echo ""
echo "--- Port 5052 (Sei Engine) -- SHOULD be reachable via Tailscale ---"
if nc -z -w 3 "$SERVER_IP" 5052 2>/dev/null; then
    echo "  PASS: TCP 5052 is reachable"
    PASS=$((PASS + 1))
else
    echo "  INFO: TCP 5052 is closed (start echo_server.py first)"
fi

echo ""
echo "--- Results ---"
echo "Correct: $PASS | Incorrect: $FAIL"

if [[ $FAIL -gt 0 ]]; then
    echo "VERIFICATION FAILED -- internal services exposed!"
    exit 1
fi

echo "VERIFICATION PASSED"
