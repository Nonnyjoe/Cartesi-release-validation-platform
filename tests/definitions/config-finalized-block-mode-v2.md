---
id: config-finalized-block-mode-v2
name: CARTESI_BLOCKCHAIN_DEFAULT_BLOCK=finalized — finality mode affects block processing (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, evm-reader, finality, v2, phase9]
csv_ids: ["9.17"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_BLOCKCHAIN_DEFAULT_BLOCK: "finalized"
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: log_contains
    component: evm-reader
    pattern: "finalized"
    timeout_seconds: 60
---

## Description
CSV test 9.17 — Set `CARTESI_BLOCKCHAIN_DEFAULT_BLOCK=finalized` and verify
that the evm-reader uses finalized blocks for processing inputs.

## Setup
Start sandbox with `CARTESI_BLOCKCHAIN_DEFAULT_BLOCK=finalized`.

## Steps
1. Submit a ping input.
2. Assert evm-reader logs reference the finalized block mode.

## Expected Behaviour
- evm-reader processes inputs only from finalized blocks.
- Log messages confirm finality mode is active.
