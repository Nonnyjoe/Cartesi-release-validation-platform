---
id: config-max-block-range-v2
name: CARTESI_BLOCKCHAIN_MAX_BLOCK_RANGE=100 — chunked log queries (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, evm-reader, v2, phase14]
csv_ids: ["14.8"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_BLOCKCHAIN_MAX_BLOCK_RANGE: "100"
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
  - type: log_contains
    service: evm-reader
    text: "range"
    timeout_seconds: 30
---

## Description
CSV test 14.8 — Set `CARTESI_BLOCKCHAIN_MAX_BLOCK_RANGE=100` (small range)
and verify the evm-reader uses chunked log queries when syncing a range larger
than 100 blocks.

## Setup
Start sandbox with `CARTESI_BLOCKCHAIN_MAX_BLOCK_RANGE=100`.

## Steps
1. Submit a ping input.
2. Assert input is indexed correctly.
3. Assert evm-reader logs mention block range or chunking.

## Expected Behaviour
- Large block ranges are split into chunks of 100.
- All inputs are indexed correctly despite smaller query windows.
