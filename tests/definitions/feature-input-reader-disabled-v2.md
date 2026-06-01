---
id: feature-input-reader-disabled-v2
name: CARTESI_FEATURE_INPUT_READER_ENABLED=false disables input scanning (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, feature-flag, input-reader, v2, phase9]
csv_ids: ["9.19"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 90
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_FEATURE_INPUT_READER_ENABLED: "false"
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
    comment: "submit input — should NOT be scanned by disabled reader"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count_exact: 0
---

## Description
CSV test 9.19 — When `CARTESI_FEATURE_INPUT_READER_ENABLED=false`, the evm-reader
should not scan for new inputs from the InputBox contract.

## Setup
This test requires the sandbox to be started with:
```
CARTESI_FEATURE_INPUT_READER_ENABLED=false
```

## Steps
1. Start node with input reader disabled.
2. Submit an input to the InputBox on-chain.
3. Assert cartesi_listInputs returns 0 inputs (input was not scanned).

## Expected Behaviour
- No inputs are indexed when the input reader is disabled.
- evm-reader still starts (healthz OK) but is in read-only mode.
