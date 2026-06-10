# Deploying Cartesi Rollups Contracts with Cannon onto Anvil

This guide explains the exact process used by the RVP sandbox provisioner to deploy
`cartesi/rollups-contracts` onto a local Anvil devnet using the
[Cannon](https://usecannon.com) build system.  Every command here is a literal
transcription of what the `rvp-cannon-deployer` container executes automatically
when a v2.x sandbox is provisioned.

---

## Repositories

| Repository | URL | Purpose |
|---|---|---|
| cartesi/rollups-contracts | https://github.com/cartesi/rollups-contracts | Smart contracts deployed onto Anvil |
| foundry-rs/foundry | https://github.com/foundry-rs/foundry | Anvil (local EVM node), Forge (Solidity compiler), Cast (RPC client) |
| usecannon/cannon | https://github.com/usecannon/cannon | Build + deployment orchestrator (replaces Hardhat deploy) |
| cartesi/rollups-node | https://github.com/cartesi/rollups-node | Node runtime that consumes the deployed contracts |

---

## Prerequisites

Install the following tools before running any commands.

### 1. Foundry (Anvil + Forge + Cast)

```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

Verify:

```bash
anvil --version
forge --version
cast --version
```

### 2. Cannon CLI

```bash
npm install -g @usecannon/cli
cannon --version
```

### 3. jq (JSON processor)

```bash
# macOS
brew install jq

# Debian / Ubuntu
apt-get install -y jq
```

---

## Overview of the Deployment Pipeline

```
Anvil (local EVM)
      ↓
rollups-contracts source tarball  ←  GitHub CDN
      ↓
forge soldeer install             (downloads Solidity deps)
      ↓
cannon build cannonfile.toml      (compiles + deploys contracts)
      ↓
cannon inspect --write-deployments (extracts contract addresses)
      ↓
JSON: { input_box, authority_factory, application_factory, ... }
```

The cannon deployer runs inside the Anvil container's **network namespace**
(`network_mode=container:<anvil_id>`) so it reaches Anvil on `localhost:8545`
without any Docker bridge DNS resolution.

---

## Step-by-Step Manual Walkthrough

All commands below assume you are working in a single terminal session and have
exported the environment variables shown in each section.

### Step 1 — Start Anvil

```bash
anvil \
  --host 0.0.0.0 \
  --port 8545 \
  --block-time 1 \
  --chain-id 31337
```

Leave this running in a separate terminal (or run it in the background with `&`).

Verify Anvil is reachable:

```bash
cast block-number --rpc-url http://localhost:8545
# Expected output: 0
```

Anvil pre-funds 10 accounts.  Account #0 is used as the deployer:

```
Address:    0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
Private key: 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
Balance:    10000 ETH
```

---

### Step 2 — Download rollups-contracts Source

Set the contracts version you want to deploy (must be a release that uses Cannon —
v2.1.0 and later):

```bash
export CONTRACTS_VERSION="2.2.0"
export TAG="v${CONTRACTS_VERSION}"
export TMP=$(mktemp -d)
```

Download the source tarball directly from GitHub:

```bash
curl -fsSL --http1.1 --retry 3 --retry-delay 2 \
  "https://github.com/cartesi/rollups-contracts/archive/refs/tags/${TAG}.tar.gz" \
  -o "${TMP}/src.tar.gz"
```

> **Why `--http1.1`?** GitHub's CDN occasionally closes HTTP/2 streams mid-transfer
> (curl exit code 18 — "partial file").  Forcing HTTP/1.1 avoids this without any
> meaningful performance cost for a single large file download.  `--retry 3` handles
> any remaining transient failures.

Extract the tarball:

```bash
tar -xzf "${TMP}/src.tar.gz" -C "${TMP}"
cd "${TMP}/rollups-contracts-${CONTRACTS_VERSION}"
```

Confirm this version uses Cannon (v2.0.0-rc.x used Hardhat and does not have this file):

```bash
ls cannonfile.toml   # must exist
```

---

### Step 3 — Install Solidity Dependencies (soldeer)

The GitHub tarball does not include the `dependencies/` directory.  Soldeer
(Foundry's native dependency manager) fetches them:

```bash
forge soldeer install
```

This reads `soldeer.toml` (or the `[soldeer]` section of `foundry.toml`) and
downloads all pinned Solidity packages into `dependencies/`.  It may take
30–60 seconds on first run.

---

### Step 4 — Build and Deploy with Cannon

```bash
export ANVIL_URL="http://localhost:8545"
export DEPLOYER_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

cannon build cannonfile.toml \
  --rpc-url "${ANVIL_URL}" \
  --chain-id 31337 \
  --private-key "${DEPLOYER_KEY}" \
  --wipe
```

Flag reference:

| Flag | Purpose |
|---|---|
| `--rpc-url` | JSON-RPC endpoint of the target chain |
| `--chain-id` | Must match Anvil's `--chain-id` (31337 = hardhat/anvil default) |
| `--private-key` | Deployer account; must have enough ETH for gas |
| `--wipe` | Clear any prior cannon package state for this package+chain; ensures a clean deployment even if cannon has a cached run |

Cannon compiles every Solidity contract via Forge, then sends deployment
transactions in dependency order as specified in `cannonfile.toml`.  On a modern
laptop this takes approximately **2–4 minutes**.

Expected tail of output:

```
✔  InputBox deployed at 0x...
✔  AuthorityFactory deployed at 0x...
✔  ApplicationFactory deployed at 0x...
✔  SelfHostedApplicationFactory deployed at 0x...
cannon build complete
```

---

### Step 5 — Extract Deployed Contract Addresses

Cannon stores the deployment state in its local registry.  The `inspect` command
writes one JSON file per contract to a directory:

```bash
# Read the package name declared in cannonfile.toml (e.g. "cartesi-rollups")
CANNON_PKG_NAME=$(grep -E '^name\s*=' cannonfile.toml | head -1 \
  | sed 's/.*=\s*"\([^"]*\)".*/\1/')

DEPLOY_DIR="/tmp/cannon-deployments"
mkdir -p "${DEPLOY_DIR}"

cannon inspect "${CANNON_PKG_NAME}:${CONTRACTS_VERSION}@main" \
  --chain-id 31337 \
  --write-deployments "${DEPLOY_DIR}" \
  --quiet
```

Each file is named after the contract and contains at minimum an `address` field:

```bash
ls "${DEPLOY_DIR}"
# InputBox.json  AuthorityFactory.json  ApplicationFactory.json  SelfHostedApplicationFactory.json  ...
```

Extract the four addresses the Cartesi node services require:

```bash
read_addr() {
  local file="${DEPLOY_DIR}/${1}.json"
  [[ -f "${file}" ]] && jq -r '.address' "${file}" || echo ""
}

INPUT_BOX=$(read_addr InputBox)
AUTH_FACTORY=$(read_addr AuthorityFactory)
APP_FACTORY=$(read_addr ApplicationFactory)
SELF_HOSTED=$(read_addr SelfHostedApplicationFactory)

jq -cn \
  --arg ib  "${INPUT_BOX}" \
  --arg af  "${AUTH_FACTORY}" \
  --arg cf  "${APP_FACTORY}" \
  --arg shf "${SELF_HOSTED}" \
  '{input_box:$ib,authority_factory:$af,application_factory:$cf,self_hosted_application_factory:$shf}'
```

Example output:

```json
{
  "input_box": "0x593e5b3D0d6752b21658b5bCBABE7c8A1b32b36c",
  "authority_factory": "0x8e78DC4F4dB99B53B65ADC6D6c2D13F60bF0B4AB",
  "application_factory": "0xA17Ef1D8a53bB8d75b7c3C1a3E72E0BD7bB0d1f3",
  "self_hosted_application_factory": "0xD9E3b2F4c5a6E1B7A8c3D4e5F6a7b8C9D0e1F2a3"
}
```

> **Note:** The exact addresses vary per deployment because Anvil resets its state
> on restart and CREATE2 salts include the chain ID and nonce.  The addresses above
> are illustrative only.

---

## Full Script (copy-paste version)

```bash
#!/usr/bin/env bash
set -euo pipefail

CONTRACTS_VERSION="${1:-2.2.0}"
ANVIL_URL="${ANVIL_URL:-http://localhost:8545}"
DEPLOYER_KEY="${DEPLOYER_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"

TAG="v${CONTRACTS_VERSION#v}"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

# ── 1. Wait for Anvil ─────────────────────────────────────────────────────────
echo "Waiting for Anvil at ${ANVIL_URL}..."
for i in $(seq 1 10); do
  cast block-number --rpc-url "${ANVIL_URL}" >/dev/null 2>&1 && break
  [[ "${i}" -eq 10 ]] && { echo "Anvil not reachable"; exit 1; }
  sleep 2
done
echo "Anvil reachable."

# ── 2. Download source ────────────────────────────────────────────────────────
echo "Downloading rollups-contracts ${TAG}..."
curl -fsSL --http1.1 --retry 3 --retry-delay 2 \
  "https://github.com/cartesi/rollups-contracts/archive/refs/tags/${TAG}.tar.gz" \
  -o "${TMP}/src.tar.gz"

tar -xzf "${TMP}/src.tar.gz" -C "${TMP}"
cd "${TMP}/rollups-contracts-${CONTRACTS_VERSION#v}"

[[ -f "cannonfile.toml" ]] || { echo "ERROR: no cannonfile.toml — pre-cannon version"; exit 1; }

# ── 3. Install Solidity deps ──────────────────────────────────────────────────
if [[ -f "soldeer.toml" || -f "soldeer.lock" ]]; then
  echo "Installing Solidity dependencies..."
  forge soldeer install
fi

# ── 4. Cannon build + deploy ──────────────────────────────────────────────────
echo "Running cannon build..."
cannon build cannonfile.toml \
  --rpc-url "${ANVIL_URL}" \
  --chain-id 31337 \
  --private-key "${DEPLOYER_KEY}" \
  --wipe

# ── 5. Extract addresses ──────────────────────────────────────────────────────
CANNON_PKG_NAME=$(grep -E '^name\s*=' cannonfile.toml | head -1 \
  | sed 's/.*=\s*"\([^"]*\)".*/\1/')

DEPLOY_DIR="${TMP}/deployments"
mkdir -p "${DEPLOY_DIR}"

cannon inspect "${CANNON_PKG_NAME}:${CONTRACTS_VERSION#v}@main" \
  --chain-id 31337 \
  --write-deployments "${DEPLOY_DIR}" \
  --quiet

read_addr() {
  local f="${DEPLOY_DIR}/${1}.json"
  [[ -f "${f}" ]] && jq -r '.address' "${f}" || echo ""
}

jq -cn \
  --arg ib  "$(read_addr InputBox)" \
  --arg af  "$(read_addr AuthorityFactory)" \
  --arg cf  "$(read_addr ApplicationFactory)" \
  --arg shf "$(read_addr SelfHostedApplicationFactory)" \
  '{input_box:$ib,authority_factory:$af,application_factory:$cf,self_hosted_application_factory:$shf}'
```

Usage:

```bash
# Deploy v2.2.0 (default)
bash deploy-rollups-contracts.sh

# Deploy a specific version
bash deploy-rollups-contracts.sh 2.1.1

# Point at a remote Anvil
ANVIL_URL=http://192.168.1.100:8545 bash deploy-rollups-contracts.sh 2.2.0
```

---

## Using the Addresses with the Cartesi Node

Pass the extracted addresses as environment variables to every service in the
Cartesi rollups-node SDK stack (`evm-reader`, `advancer`, `validator`, `claimer`,
`jsonrpc-api`):

```bash
export CARTESI_CONTRACTS_INPUT_BOX_ADDRESS="<input_box value>"
export CARTESI_CONTRACTS_AUTHORITY_FACTORY_ADDRESS="<authority_factory value>"
export CARTESI_CONTRACTS_APPLICATION_FACTORY_ADDRESS="<application_factory value>"
export CARTESI_CONTRACTS_SELF_HOSTED_APPLICATION_FACTORY_ADDRESS="<self_hosted value>"
```

Docker Compose example (abbreviated):

```yaml
services:
  evm-reader:
    image: cartesi/rollups-runtime:2.0.0-alpha.34
    command: cartesi-rollups-evm-reader --default-block latest
    environment:
      CARTESI_BLOCKCHAIN_HTTP_ENDPOINT: http://anvil:8545
      CARTESI_BLOCKCHAIN_WS_ENDPOINT:  ws://anvil:8545
      CARTESI_BLOCKCHAIN_ID: "31337"
      CARTESI_CONTRACTS_INPUT_BOX_ADDRESS: "${CARTESI_CONTRACTS_INPUT_BOX_ADDRESS}"
      CARTESI_CONTRACTS_AUTHORITY_FACTORY_ADDRESS: "${CARTESI_CONTRACTS_AUTHORITY_FACTORY_ADDRESS}"
      CARTESI_CONTRACTS_APPLICATION_FACTORY_ADDRESS: "${CARTESI_CONTRACTS_APPLICATION_FACTORY_ADDRESS}"
      CARTESI_CONTRACTS_SELF_HOSTED_APPLICATION_FACTORY_ADDRESS: "${CARTESI_CONTRACTS_SELF_HOSTED_APPLICATION_FACTORY_ADDRESS}"
```

---

## How the RVP System Does This Automatically

The RVP sandbox provisioner automates all of the above through two files:

| File | Role |
|---|---|
| `sandbox-base/cannon-deployer/Dockerfile` | Builds `rvp-cannon-deployer:<version>` image containing Node.js, Cannon CLI, Forge, Cast, and `deploy-contracts.sh` |
| `sandbox-base/cannon-deployer/deploy-contracts.sh` | Runs inside the image; performs steps 1–5 above and prints the JSON address blob to stdout |
| `services/sandbox-manager/provisioner.py` | `_deploy_contracts_sync()` — builds/caches the deployer image, starts it with `network_mode=container:<anvil_id>` so it shares Anvil's network namespace, waits for it to exit, and parses the JSON from stdout |

The deployer container is always started with `network_mode=container:<anvil_container_id>`
rather than on the sandbox bridge network.  This means:

- `localhost:8545` inside the deployer resolves to Anvil directly — no Docker DNS
  lookup, no bridge hairpin routing.
- Outbound traffic (the GitHub tarball download) still routes through the host
  network normally.

The deployer image is built once per `contracts_version` and cached locally as
`rvp-cannon-deployer:<version>`.  Subsequent sandboxes using the same version
skip the build entirely.

---

## Supported contracts_version Values

Only versions that include `cannonfile.toml` can be deployed by this tool.
The cannon migration in `rollups-contracts` happened after the v2.0.0-rc series.

Confirmed working versions:

| Version | Tag | Notes |
|---|---|---|
| 2.1.1 | v2.1.1 | First stable cannon release |
| 2.2.0 | v2.2.0 | Current stable |

To check whether a given version uses Cannon:

```bash
curl -fsSL --http1.1 \
  "https://raw.githubusercontent.com/cartesi/rollups-contracts/v2.2.0/cannonfile.toml" \
  | head -5
# If the file exists and starts with [setting] or [contract], it uses Cannon.
```

---

## Troubleshooting

### `curl: (18) HTTP/2 stream 1 was not closed cleanly`

GitHub's CDN dropped the HTTP/2 connection mid-transfer.  The `--http1.1` flag
prevents this class of error; `--retry 3` handles any remaining transient failures.
If you see this error without `--http1.1`, add it.

### `cannon build` fails with soldeer network error

This means `forge soldeer install` was skipped or failed.  Run it manually from
the extracted source directory:

```bash
cd "${TMP}/rollups-contracts-${CONTRACTS_VERSION}"
forge soldeer install
```

### `cannonfile.toml: no such file or directory`

The contracts version pre-dates the Cannon migration.  Use v2.1.1 or later.

### `could not find InputBox address` after `cannon inspect`

`cannon inspect` found no deployments for the given package+version+chain-id tuple.
This usually means `cannon build` was not run with `--wipe` and is reading a
cached (stale) state.  Re-run with `--wipe`.

### Anvil not reachable

Check that Anvil is running and listening on the expected address:

```bash
cast block-number --rpc-url http://localhost:8545
```

If running the deployer as a Docker container with
`network_mode=container:<anvil_id>`, verify that the Anvil container is still
running and was started before the deployer.
