---
id: jsonrpc-list-epochs-v2
name: cartesi_listEpochs pagination and status filters (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, epochs, pagination, v2, phase8]
csv_ids: ["8.5"]
release_introduced: v2.0.0
component: jsonrpc
priority: high
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_listEpochs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 8.5 — Verify `cartesi_listEpochs` returns epochs for the application
with correct pagination envelope and status filters.

## Steps
1. Call `cartesi_listEpochs` with the app address.
2. Assert at least one epoch is returned.

## Expected Behaviour
- Response contains `result.data` with ≥1 epoch.
- Each epoch has an `index`, `status`, and `firstBlock` / `lastBlock`.
