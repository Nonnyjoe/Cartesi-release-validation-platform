---
id: performance-100-inputs-v2
name: Process 100 inputs in a single epoch within 60s (v2.x)
version: 1
min_node_major_version: 2
tags: [performance, throughput, v2, phase17]
csv_ids: ["17.1"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_listApplications
    use_app_address: false
    stress_count: 100
    comment: "submit 100 rapid inputs via stress_count"
  - type: json_rpc
    method: cartesi_getProcessedInputCount
    use_app_address: true
    expect_has_field: "data"
---

## Description
CSV test 17.1 — Submit 100 inputs in a single epoch and verify all reach
PROCESSED status within 60 seconds.

## Steps
1. Send 100 concurrent inputs to the node.
2. Poll cartesi_getProcessedInputCount until it reaches 100 or timeout.

## Expected Behaviour
- All 100 inputs are processed within 60s.
- No dropped inputs.
