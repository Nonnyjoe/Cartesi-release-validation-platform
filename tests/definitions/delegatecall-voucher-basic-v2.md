---
id: delegatecall-voucher-basic-v2
name: Emit basic DELEGATECALL voucher via /delegate-call-voucher endpoint (v2.x)
version: 1
min_node_major_version: 2
tags: [output, voucher, delegatecall, v2, phase6]
csv_ids: ["6.1"]
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
    payload: '{"action":"delegatecall_voucher","target":"0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef","data":"0xdeadbeef"}'
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_interval: 3
    poll_timeout: 120
---

## Description
CSV test 6.1 — Trigger a DELEGATECALL voucher from the application and verify
it appears in cartesi_listOutputs as a delegate-call-voucher type.

## Steps
1. Submit an action that causes the VM to emit a DelegateCall voucher.
2. Poll cartesi_listOutputs for the delegate-call-voucher output.

## Expected Behaviour
- DelegateCall voucher appears with correct target address and calldata.
- Voucher type is distinct from regular call vouchers.
