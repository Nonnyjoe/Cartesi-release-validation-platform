---
id: security-sdk-response-cap-v2
name: JS SDK response size cap (~600KB) — known limitation (v2.x)
version: 1
min_node_major_version: 2
tags: [limits, sdk, json-rpc, v2, phase11]
csv_ids: ["11.7"]
release_introduced: v2.0.0
component: jsonrpc
priority: low
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a226c6172676572657370 6f6e7365222c2273697a65223a22373030 6b62227d"
    comment: "generate a 700KB output (exceeds JS SDK ~600KB cap)"
  - type: json_rpc
    method: cartesi_listOutputs
    use_app_address: true
    expect_count: 1
    comment: "node API returns full 700KB but JS SDK may truncate at ~600KB"
---

## Description
CSV test 11.7 — Document the known JS SDK response size limitation (~600KB).
The node API serves full responses but the JS SDK client may truncate at ~600KB.

## Steps
1. Generate an output larger than 600KB from the VM.
2. Assert the output appears via cartesi_listOutputs (full node API response).
3. Note: JS SDK consumers may experience truncation at ~600KB.

## Expected Behaviour
- Node API returns the full response regardless of size.
- Known limitation: JS SDK wrapping may truncate at ~600KB.
