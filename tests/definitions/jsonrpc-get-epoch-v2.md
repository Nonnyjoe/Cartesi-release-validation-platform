---
id: jsonrpc-get-epoch-v2
name: cartesi_getEpoch fetch specific epoch index (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, epochs, v2, phase8]
csv_ids: ["8.6"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0xdeadbeef"
  - type: json_rpc
    method: cartesi_getEpoch
    use_app_address: true
    use_last_epoch: true
---

## Description
CSV test 8.6 — Verify `cartesi_getEpoch` fetches epoch 0 by index.

## Steps
1. Call `cartesi_getEpoch` with the app address and epoch index 0.
2. Assert the response returns the epoch object.

## Expected Behaviour
- Response contains epoch 0's object with status and block range.
