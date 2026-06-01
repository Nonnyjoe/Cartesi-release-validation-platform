---
id: chaos-hard-kill-all-v2
name: Hard-kill all containers mid-execution — disaster recovery (v2.x)
version: 1
min_node_major_version: 2
tags: [chaos, persistence, disaster-recovery, standalone, v2, phase9]
csv_ids: ["9.11"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 300
group: chaos
suite_ids: [chaos]
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a227265676973746572227d"
    comment: "create data before chaos event"
  - type: service_restart
    service: advancer
    verify_path: /readyz
    verify_timeout: 90
  - type: service_restart
    service: jsonrpc
    verify_path: /readyz
    verify_timeout: 60
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 9.11 — Hard-kill all node containers mid-execution and verify the
system recovers and data integrity is maintained.

## Steps
1. Submit a register input.
2. Hard restart advancer and jsonrpc containers simultaneously.
3. Verify all services recover.
4. Assert the previously submitted input is still accessible.

## Expected Behaviour
- System recovers from hard kill within 90s.
- All previously indexed data is intact.
- Processing resumes correctly.
