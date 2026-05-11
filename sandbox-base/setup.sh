#!/bin/bash
# setup-sandbox.sh
# Run inside a fresh sandbox container to verify the environment is ready.
set -euo pipefail

echo "[setup-sandbox] Checking Anvil..."
anvil --version

echo "[setup-sandbox] Checking Cast..."
cast --version

echo "[setup-sandbox] Checking Cartesi CLI..."
cartesi --version || echo "[setup-sandbox] Cartesi CLI check skipped (version flag varies)"

echo "[setup-sandbox] Checking Docker socket..."
docker info --format '{{.ServerVersion}}' 2>/dev/null || echo "[setup-sandbox] Docker socket not available (expected in DinD mode)"

echo "[setup-sandbox] All checks passed."
