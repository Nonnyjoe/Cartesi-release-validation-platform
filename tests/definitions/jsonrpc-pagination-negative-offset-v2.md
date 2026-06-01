---
id: jsonrpc-pagination-negative-offset-v2
name: JSON-RPC pagination with negative offset returns error (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, pagination, edge-cases, v2, phase8]
csv_ids: ["8.19"]
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
    pagination_offset: -1
    expect_error: true
---

## Description
CSV test 8.19 — Verify `cartesi_listInputs` with a negative offset returns an
INVALID_PARAMS error.

## Steps
1. Call `cartesi_listInputs` with offset=-1.
2. Assert the response contains an error.

## Expected Behaviour
- Response contains `error` with code -32602 (INVALID_PARAMS).
