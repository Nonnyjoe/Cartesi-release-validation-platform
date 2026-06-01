---
id: jsonrpc-pagination-max-limit-v2
name: JSON-RPC pagination with limit=10000 max (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, pagination, edge-cases, v2, phase8]
csv_ids: ["8.35"]
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
    pagination_limit: 10000
---

## Description
CSV test 8.35 — Verify `cartesi_listInputs` with `limit=10000` (max) honours
the limit without truncation or error.

## Steps
1. Call `cartesi_listInputs` with limit=10000.
2. Assert the call succeeds (no error).

## Expected Behaviour
- Response succeeds with up to 10000 inputs.
- The node applies the max limit without crashing.
