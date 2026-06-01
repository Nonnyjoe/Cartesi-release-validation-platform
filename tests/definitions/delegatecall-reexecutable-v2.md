---
id: delegatecall-reexecutable-v2
name: Re-executable DELEGATECALL voucher — can execute multiple times (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, delegatecall, voucher, v2, phase6]
csv_ids: ["6.8"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 360
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2272656578656375 7461626c655f766f756368657222 7d"
    comment: "request a re-executable DELEGATECALL voucher"
  - type: voucher_v2
    mode: execute
    expect_count: 1
    poll_timeout: 240
---

## Description
CSV test 6.8 — Emit a re-executable DELEGATECALL voucher and verify it can be
executed more than once (unlike regular vouchers which have replay protection).

## Steps
1. Submit an input requesting a re-executable DELEGATECALL voucher.
2. Execute the voucher once.
3. Verify the voucher can be executed again (no replay protection).

## Expected Behaviour
- Re-executable voucher executes successfully on first call.
- Second execution also succeeds (no burned flag set).
