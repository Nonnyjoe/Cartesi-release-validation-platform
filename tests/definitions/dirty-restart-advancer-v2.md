---
id: dirty-restart-advancer-v2
name: Restart advancer with pending inputs — resumes without corruption (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, dirty-restart, advancer, standalone, persistence, v2, phase9]
csv_ids: ["9.1"]
release_introduced: v2.0.0
component: advancer
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
    comment: "submit input before restart to create pending state"
  - type: service_restart
    service: advancer
    verify_path: /readyz
    verify_timeout: 90
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 9.1 — Submit an input, restart the advancer while it may be
processing, then verify inputs are not lost or duplicated.

## Steps
1. Submit a ping input to the InputBox.
2. Restart the advancer container.
3. Wait for advancer to become healthy.
4. Assert the input appears in cartesi_listInputs.

## Expected Behaviour
- No inputs are lost on dirty restart.
- Processing resumes from last checkpoint without duplication or corruption.
