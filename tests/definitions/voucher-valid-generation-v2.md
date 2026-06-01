---
id: voucher-valid-generation-v2
name: Generate valid voucher — basic voucher generation (v2.x)
version: 1
min_node_major_version: 2
tags: [output, voucher, v2, phase5]
csv_ids: ["5.4"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 240
requires:
  - anvil
  - cartesi-node-v2
  - claimer
assertions:
  - type: chain_tx
    payload: '{"action":"generate_voucher","to":"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266","data":"0xdeadbeef"}'
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_interval: 3
    poll_timeout: 120
---

## Description
CSV test 5.4 — Trigger the application to generate a valid voucher and verify
it appears in cartesi_listOutputs.

## Steps
1. Send a generate_voucher action with a target address and calldata.
2. Poll for the voucher in cartesi_listOutputs.

## Expected Behaviour
- Voucher appears with correct target address and calldata.
- Voucher status is UNEXECUTED.
