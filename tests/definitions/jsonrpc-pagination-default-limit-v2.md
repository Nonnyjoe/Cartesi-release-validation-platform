---
id: jsonrpc-pagination-default-limit-v2
name: JSON-RPC pagination with no limit param uses default of 50 (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, pagination, v2, phase8]
csv_ids: ["8.36"]
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
    path: pagination.limit
    value: 50
---

## Description
CSV test 8.36 — Verify `cartesi_listInputs` with no limit parameter applies
a default limit of 50.

## Steps
1. Call `cartesi_listInputs` with no limit parameter.
2. Assert `result.pagination.limit == 50`.

## Expected Behaviour
- The default page size of 50 is applied when no limit is specified.
