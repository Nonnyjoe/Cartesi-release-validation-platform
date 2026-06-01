---
id: delegatecall-paid-voucher-v2
name: DELEGATECALL paid voucher — rewards the executor (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, delegatecall, voucher, v2, phase6]
csv_ids: ["6.4"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270616964 5f76 6f756368657222 7d"
    comment: "request a paid DELEGATECALL voucher (rewards executor)"
  - type: voucher_v2
    mode: execute
    expect_count: 1
    poll_timeout: 240
---

## Description
CSV test 6.4 — Emit a DELEGATECALL voucher that pays a reward to whoever
executes it on-chain, and verify the payment mechanism works correctly.

## Steps
1. Submit an input requesting a paid DELEGATECALL voucher.
2. Wait for epoch claim.
3. Execute the voucher and verify the executor receives the payment.

## Expected Behaviour
- DELEGATECALL voucher includes payment logic.
- Executor wallet balance increases after successful execution.
