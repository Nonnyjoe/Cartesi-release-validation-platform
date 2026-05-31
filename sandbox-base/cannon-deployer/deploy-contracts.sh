#!/usr/bin/env bash
# deploy-contracts.sh
# Deploys rollups-contracts via cannon build/inspect and prints the four
# contract addresses to stdout as a compact JSON object.
#
# This script runs inside the Anvil container's network namespace
# (network_mode=container:<anvil_id>), so ANVIL_URL=http://localhost:8545.
#
# Required env vars:
#   CONTRACTS_VERSION  e.g. "2.2.0" or "v2.1.1" (leading v stripped internally)
#   ANVIL_URL          always "http://localhost:8545" (shared network namespace)
#   DEPLOYER_KEY       Anvil account #0 private key
#
# On success: prints a single compact JSON object to stdout with the four
# contract addresses the Cartesi node services need.
# On failure: exits non-zero; stderr contains the error details.
set -euo pipefail

: "${CONTRACTS_VERSION:?CONTRACTS_VERSION env var is required}"
: "${ANVIL_URL:?ANVIL_URL env var is required}"
: "${DEPLOYER_KEY:?DEPLOYER_KEY env var is required}"

# ── Wait for Anvil to be reachable ───────────────────────────────────────────
# The deployer runs in the Anvil container's network namespace (network_mode=
# container:<id>), so ANVIL_URL=http://localhost:8545.  Anvil should already
# be ready (provisioner confirmed health), but we retry briefly to absorb any
# last-millisecond startup lag.
echo "[cannon-deployer] Waiting for Anvil at ${ANVIL_URL}..." >&2
ANVIL_RETRIES=10
ANVIL_WAIT=2
for i in $(seq 1 ${ANVIL_RETRIES}); do
  cast block-number --rpc-url "${ANVIL_URL}" >/dev/null 2>&1 && {
    echo "[cannon-deployer] Anvil is reachable (attempt ${i}/${ANVIL_RETRIES})" >&2
    break
  }
  if [[ "${i}" -eq "${ANVIL_RETRIES}" ]]; then
    echo "[cannon-deployer] ERROR: Anvil not reachable at ${ANVIL_URL} after $((ANVIL_RETRIES * ANVIL_WAIT))s" >&2
    cast block-number --rpc-url "${ANVIL_URL}" >&2 || true
    exit 1
  fi
  echo "[cannon-deployer] Anvil not ready (attempt ${i}/${ANVIL_RETRIES}), retrying in ${ANVIL_WAIT}s..." >&2
  sleep "${ANVIL_WAIT}"
done

# Normalize: strip any leading 'v' so that both "2.2.0" and "v2.1.1" (as
# stored in the release catalog) produce TAG="v2.x.x" — not "vv2.1.1".
CONTRACTS_VERSION="${CONTRACTS_VERSION#v}"
TAG="v${CONTRACTS_VERSION}"
TMP="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP}"
}
trap cleanup EXIT

echo "[cannon-deployer] Downloading rollups-contracts ${TAG}..." >&2
curl -fsSL --http1.1 --retry 3 --retry-delay 2 \
  "https://github.com/cartesi/rollups-contracts/archive/refs/tags/${TAG}.tar.gz" \
  -o "${TMP}/src.tar.gz"

tar -xzf "${TMP}/src.tar.gz" -C "${TMP}"
cd "${TMP}/rollups-contracts-${CONTRACTS_VERSION}"

# Verify this version uses cannon — older releases (e.g. 2.0.0-rc.x) used
# hardhat and git submodules; cannon was adopted later.  Fail fast with a
# clear message rather than a confusing soldeer network error.
if [[ ! -f "cannonfile.toml" ]]; then
  echo "[cannon-deployer] ERROR: rollups-contracts ${CONTRACTS_VERSION} has no cannonfile.toml" >&2
  echo "[cannon-deployer] This version pre-dates the cannon migration and cannot be deployed by this tool." >&2
  exit 1
fi

# Install Solidity dependencies via soldeer (rollups-contracts v2.x with cannon
# uses soldeer — the GitHub tarball does not include the dependencies/ dir)
if [[ -f "soldeer.toml" ]] || [[ -f "soldeer.lock" ]]; then
  echo "[cannon-deployer] Installing Solidity dependencies (forge soldeer install)..." >&2
  forge soldeer install >&2 2>&1
else
  echo "[cannon-deployer] No soldeer config found — skipping soldeer install" >&2
fi

echo "[cannon-deployer] Running cannon build against ${ANVIL_URL}..." >&2
cannon build cannonfile.toml \
  --rpc-url "${ANVIL_URL}" \
  --chain-id 31337 \
  --private-key "${DEPLOYER_KEY}" \
  --wipe > /tmp/cannon-build.log 2>&1 || {
    echo "[cannon-deployer] ERROR: cannon build failed" >&2
    cat /tmp/cannon-build.log >&2
    exit 1
  }
# Echo build log to stderr for provisioner log visibility
cat /tmp/cannon-build.log >&2

# ── Extract deployed addresses via cannon inspect --write-deployments ─────────
# cannon inspect writes one JSON file per contract to a directory; each file
# has at minimum an "address" field. This is more reliable than parsing build
# log output (which omits address lines when CREATE2 contracts are cached).
echo "[cannon-deployer] Extracting deployed addresses..." >&2

# Read the package name from cannonfile.toml (e.g. "cartesi-rollups")
CANNON_PKG_NAME=$(grep -E '^name\s*=' cannonfile.toml | head -1 \
  | sed 's/.*=\s*"\([^"]*\)".*/\1/')

DEPLOY_DIR="/tmp/cannon-deployments"
mkdir -p "${DEPLOY_DIR}"

cannon inspect "${CANNON_PKG_NAME}:${CONTRACTS_VERSION}@main" \
  --chain-id 31337 \
  --write-deployments "${DEPLOY_DIR}" \
  --quiet >&2 2>&1

read_addr() {
  local name="$1"
  local file="${DEPLOY_DIR}/${name}.json"
  if [[ -f "${file}" ]]; then
    jq -r '.address' "${file}"
  else
    echo ""
  fi
}

INPUT_BOX="$(read_addr 'InputBox')"
AUTH_FACTORY="$(read_addr 'AuthorityFactory')"
APP_FACTORY="$(read_addr 'ApplicationFactory')"
SELF_HOSTED="$(read_addr 'SelfHostedApplicationFactory')"

# Portal contracts — deployed by the same cannonfile; extract if present.
# Empty string is acceptable — provisioner falls back to deterministic defaults.
ETHER_PORTAL="$(read_addr 'EtherPortal')"
ERC20_PORTAL="$(read_addr 'ERC20Portal')"
ERC721_PORTAL="$(read_addr 'ERC721Portal')"
ERC1155_PORTAL="$(read_addr 'ERC1155SinglePortal')"

if [[ -z "${INPUT_BOX}" || "${INPUT_BOX}" == "null" ]]; then
  echo "[cannon-deployer] ERROR: could not find InputBox address" >&2
  echo "[cannon-deployer] Files in ${DEPLOY_DIR}:" >&2
  ls "${DEPLOY_DIR}" >&2 2>/dev/null || true
  exit 1
fi

jq -cn \
  --arg ib     "${INPUT_BOX}" \
  --arg af     "${AUTH_FACTORY}" \
  --arg cf     "${APP_FACTORY}" \
  --arg shf    "${SELF_HOSTED}" \
  --arg ether  "${ETHER_PORTAL}" \
  --arg erc20  "${ERC20_PORTAL}" \
  --arg erc721 "${ERC721_PORTAL}" \
  --arg erc1155 "${ERC1155_PORTAL}" \
  '{input_box:$ib,authority_factory:$af,application_factory:$cf,self_hosted_application_factory:$shf,ether_portal:$ether,erc20_portal:$erc20,erc721_portal:$erc721,erc1155_portal:$erc1155}'
