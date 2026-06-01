---
id: jsonrpc-get-output-v2
name: cartesi_getOutput fetch specific output index (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, outputs, v2, phase8]
csv_ids: ["8.12"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a227265676973746572227d"
  - type: json_rpc
    method: cartesi_getOutput
    use_app_address: true
    params: ["0x0"]
---

## Description
CSV test 8.12 — Verify `cartesi_getOutput` fetches output index 0.

## Steps
1. Submit a register action to ensure at least one output exists.
2. Call `cartesi_getOutput` with the app address and index 0.
3. Assert the output object is returned.

## Expected Behaviour
- Response contains the output object with `index`, `inputIndex`, and `payload`.
