---
id: jsonrpc-list-outputs-v2
ai_allowed: true
name: cartesi_listOutputs pagination and type/address filter (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, outputs, pagination, v2, phase8]
csv_ids: ["8.11"]
release_introduced: v2.0.0
component: jsonrpc
priority: high
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a227265676973746572227d"
    comment: '{"action":"register"} — triggers notice output'
  - type: json_rpc
    method: cartesi_listOutputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 8.11 — Verify `cartesi_listOutputs` returns outputs with correct
pagination and type/address filters.

## Steps
1. Submit a register action to trigger a notice output.
2. Call `cartesi_listOutputs` with the app address.
3. Assert at least one output is returned.

## Expected Behaviour
- Response contains `result.data` with ≥1 output (notice or voucher).
- Each output has `index`, `inputIndex`, and `payload`.
