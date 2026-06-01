---
id: notice-generation-v2
name: Notice Generation — valid notice (v2.x)
version: 1
min_node_major_version: 2
tags: [output, notice, vm, core, v2, phase5]
csv_ids: ["5.1"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: '{"action":"register"}'
  - type: notice_check
    min_count: 1
    poll_interval: 3
    poll_timeout: 120
  - type: json_rpc
    method: cartesi_listOutputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 5.1 — Sends a JSON `register` action that causes the student-tracker
application to emit a notice, then verifies the notice is indexed.

The payload `0x7b22616374696f6e223a22726567697374657222...` is
`{"action":"register","name":"TestUser","reg_number":"T001"}` hex-encoded.

## Steps
1. Submit a `register` action as a hex-encoded JSON payload.
2. Poll cartesi_listOutputs and assert at least 1 notice is returned.
3. Verify cartesi_listOutputs shows ≥1 output.

## Expected Behaviour
- The application emits a `student_registered` notice.
- cartesi_listOutputs returns ≥1 entry.
