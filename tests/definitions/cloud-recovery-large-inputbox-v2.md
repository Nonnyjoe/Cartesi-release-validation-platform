---
id: cloud-recovery-large-inputbox-v2
name: Node resync with large InputBox — catch-up performance (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cloud, recovery, evm-reader, performance, v2, phase9]
csv_ids: ["9.14"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 600
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 50
    poll_timeout: 300
    comment: "after 50 inputs exist, restart the evm-reader to test catch-up"
  - type: service_restart
    service: evm-reader
    wait_healthy: true
    timeout: 120
  - type: log_contains
    component: evm-reader
    pattern: "synced"
    timeout_seconds: 120
---

## Description
CSV test 9.14 — Pre-populate a large InputBox, then restart the evm-reader and
verify it catches up to the current block height within acceptable time.

## Steps
1. Ensure 50+ inputs exist in the InputBox (pre-seeded).
2. Restart the evm-reader.
3. Assert evm-reader resyncs and logs "synced" state.
4. Assert all inputs are indexed correctly.

## Expected Behaviour
- evm-reader performs efficient catch-up using chunked log queries.
- All historical inputs are indexed on restart.
