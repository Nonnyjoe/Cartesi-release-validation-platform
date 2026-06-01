---
id: config-wrong-chain-id-v2
name: Wrong CARTESI_BLOCKCHAIN_ID causes chain ID mismatch failure (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, startup, chain-id, v2, phase14]
csv_ids: ["14.10"]
release_introduced: v2.0.0
component: evm-reader
priority: high
timeout_seconds: 60
env_overrides:
  CARTESI_BLOCKCHAIN_ID: "1"
requires:
  - anvil
assertions:
  - type: log_contains
    component: evm-reader
    pattern: "chain"
    timeout_seconds: 30
    comment: "evm-reader should log chain ID mismatch error on startup"
---

## Description
CSV test 14.10 — Set `CARTESI_BLOCKCHAIN_ID` to the wrong chain ID (1 = Mainnet
vs 31337 = Anvil) and verify startup fails with a chain ID mismatch error.

## Setup
Start sandbox with `CARTESI_BLOCKCHAIN_ID=1` while Anvil uses chain ID 31337.

## Steps
1. Start node with wrong chain ID configuration.
2. Assert evm-reader logs a chain ID mismatch or startup failure.

## Expected Behaviour
- evm-reader fails fast with a clear chain ID validation error.
