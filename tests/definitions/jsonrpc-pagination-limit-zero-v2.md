---
id: jsonrpc-pagination-limit-zero-v2
name: JSON-RPC pagination with limit=0 boundary test (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, pagination, edge-cases, v2, phase8]
csv_ids: ["8.17"]
release_introduced: v2.0.0
component: jsonrpc
priority: low
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    pagination_limit: 0
    expect_has_field: "data"
---

## Description
CSV test 8.17 — Verify `cartesi_listInputs` with `limit=0` returns an empty
data array (boundary condition).

## Steps
1. Call `cartesi_listInputs` with limit=0 pagination parameter.
2. Assert the data array is empty (count == 0).

## Expected Behaviour
- Response has `result.data` as an empty array.
- No error is returned; limit=0 is treated as "return nothing".
