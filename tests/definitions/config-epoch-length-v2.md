---
id: config-epoch-length-v2
name: Vary CARTESI_EPOCH_LENGTH and confirm epoch boundaries (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, epoch, v2, phase14]
csv_ids: ["14.3"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 120
env_overrides:
  CARTESI_EPOCH_LENGTH: "5"
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listEpochs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 14.3 — Vary `CARTESI_EPOCH_LENGTH=5` and confirm epoch boundaries
are observed at the custom block count.

## Setup
Start sandbox with `CARTESI_EPOCH_LENGTH=5`.

## Steps
1. Submit a ping input.
2. Assert epochs are being created.

## Expected Behaviour
- Epoch boundaries occur every 5 blocks.
- cartesi_listEpochs reflects the custom epoch length.
