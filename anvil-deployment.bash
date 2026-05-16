#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-2.2.0}"
TAG="v${VERSION}"

TMP_DIR="$(mktemp -d)"
ANVIL_PID=""

cleanup() {
  if [[ -n "${ANVIL_PID}" ]]; then
    kill "${ANVIL_PID}" >/dev/null 2>&1 || true
  fi

  if [[ -d "${TMP_DIR}" ]]; then
    echo "Deleting temporary files: ${TMP_DIR}"
    rm -rf "${TMP_DIR}"
  fi
}

trap cleanup EXIT

echo "Using temp directory: ${TMP_DIR}"

curl -fsSL \
  "https://github.com/cartesi/rollups-contracts/archive/refs/tags/${TAG}.tar.gz" \
  -o "${TMP_DIR}/rollups-contracts.tar.gz"

tar -xzf "${TMP_DIR}/rollups-contracts.tar.gz" -C "${TMP_DIR}"

cd "${TMP_DIR}/rollups-contracts-${VERSION}"

anvil \
  --chain-id 31337 \
  --host 127.0.0.1 \
  --port 8545 \
  > "${TMP_DIR}/anvil.log" 2>&1 &

ANVIL_PID=$!

sleep 2

cannon build cannonfile.toml \
  --rpc-url http://127.0.0.1:8545 \
  --chain-id 31337 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80