---
id: jsonrpc-get-report-v2
name: cartesi_getReport fetch specific report index (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, reports, v2, phase8]
csv_ids: ["8.14"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0xdeadbeef"
  - type: json_rpc
    method: cartesi_getReport
    use_app_address: true
    params: ["0x0"]
---

## Description
CSV test 8.14 — Verify `cartesi_getReport` fetches report index 0.

## Steps
1. Submit any input to ensure at least one report exists.
2. Call `cartesi_getReport` with the app address and index 0.
3. Assert the report object is returned.

## Expected Behaviour
- Response contains the report object with `index`, `inputIndex`, and `payload`.
