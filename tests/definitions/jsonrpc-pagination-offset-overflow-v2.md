---
id: jsonrpc-pagination-offset-overflow-v2
name: JSON-RPC pagination with offset > max items (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, pagination, edge-cases, v2, phase8]
csv_ids: ["8.18"]
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
    pagination_offset: 999999
    expect_count_exact: 0
---

## Description
CSV test 8.18 — Verify `cartesi_listInputs` with offset > total items returns
an empty data array without error.

## Steps
1. Call `cartesi_listInputs` with offset=999999 (beyond all existing inputs).
2. Assert the data array is empty.

## Expected Behaviour
- Response has `result.data` as an empty array.
- Pagination total still reflects the actual count.
