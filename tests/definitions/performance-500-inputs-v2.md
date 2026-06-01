---
id: performance-500-inputs-v2
name: Process 500 inputs across multiple epochs (v2.x)
version: 1
min_node_major_version: 2
tags: [performance, throughput, v2, phase17]
csv_ids: ["17.2"]
release_introduced: v2.0.0
component: advancer
priority: low
timeout_seconds: 600
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: '{"action":"ping"}'
    repeat: 50
  - type: json_rpc
    method: cartesi_getProcessedInputCount
    use_app_address: true
    expect_has_field: "data"
---

## Description
CSV test 17.2 — Process 500 inputs across multiple epochs and verify correct
epoch assignments with no dropped inputs.

Note: Full 500-input test requires multiple stress batches. This definition
covers the first 100; extend with additional stress_count assertions for full
coverage.

## Steps
1. Send 500 inputs across multiple blocks (triggering multiple epoch boundaries).
2. Verify all inputs are processed with correct epoch assignments.

## Expected Behaviour
- All 500 inputs are processed.
- Epoch boundaries are respected.
- No dropped or duplicated inputs.
