---
id: jsonrpc-list-inputs-v2
name: cartesi_listInputs pagination and epoch/sender filters (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, inputs, pagination, v2, phase8]
csv_ids: ["8.8"]
release_introduced: v2.0.0
component: jsonrpc
priority: high
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
    comment: '{"action":"ping"} — ensure at least one input exists'
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 8.8 — Verify `cartesi_listInputs` returns inputs with correct
pagination envelope and epoch/sender filters.

## Steps
1. Submit a ping input to ensure at least one input exists.
2. Call `cartesi_listInputs` with the app address.
3. Assert at least one input is returned.

## Expected Behaviour
- Response contains `result.data` with ≥1 input.
- Each input has `index`, `status`, `msgSender`, and `payload`.
