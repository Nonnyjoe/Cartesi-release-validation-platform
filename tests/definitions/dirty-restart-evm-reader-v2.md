---
id: dirty-restart-evm-reader-v2
name: Restart evm-reader while inputs are being sent — no missed L1 events (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, dirty-restart, evm-reader, standalone, persistence, v2, phase9]
csv_ids: ["9.4"]
release_introduced: v2.0.0
component: evm-reader
priority: critical
timeout_seconds: 240
group: dirty_restart
suite_ids: [dirty_restart]
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
    comment: "send input before restart"
  - type: service_restart
    service: evm-reader
    verify_path: /readyz
    verify_timeout: 90
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e6732227d"
    comment: "send another input after restart"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 2
---

## Description
CSV test 9.4 — Restart evm-reader while inputs are being submitted and verify
no L1 events are missed.

## Steps
1. Submit input #1 before restarting evm-reader.
2. Restart evm-reader.
3. Submit input #2 after restart.
4. Assert both inputs appear in cartesi_listInputs.

## Expected Behaviour
- evm-reader re-scans from last processed block on restart.
- No events are skipped or duplicated.
