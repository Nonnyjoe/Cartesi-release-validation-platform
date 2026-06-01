---
id: delegatecall-timelocked-v2
name: Time-locked DELEGATECALL voucher — execute only after timestamp (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, delegatecall, voucher, time-lock, v2, phase6]
csv_ids: ["6.5"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2274696d656c6f636b65645f766f756368657222 7d"
    comment: "request a time-locked DELEGATECALL voucher"
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_timeout: 120
---

## Description
CSV test 6.5 — Emit a time-locked DELEGATECALL voucher that can only be
executed after a specific timestamp has passed.

## Steps
1. Submit an input requesting a time-locked DELEGATECALL voucher.
2. Verify the voucher is emitted.
3. (Execution before the lock time should revert.)

## Expected Behaviour
- Time-locked voucher is emitted correctly.
- Voucher payload contains the timestamp lock condition.
