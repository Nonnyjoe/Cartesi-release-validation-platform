---
id: jsonrpc-get-input-v2
name: cartesi_getInput fetch specific input index (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, inputs, v2, phase8]
csv_ids: ["8.9"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_getInput
    use_app_address: true
    params: ["0x0"]
---

## Description
CSV test 8.9 — Verify `cartesi_getInput` fetches input index 0.

## Steps
1. Submit a ping input to ensure at least one input exists.
2. Call `cartesi_getInput` with the app address and index 0.
3. Assert the input object is returned.

## Expected Behaviour
- Response contains the input object with `index`, `status`, and `payload`.
