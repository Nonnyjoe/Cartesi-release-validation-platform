---
id: delegatecall-expirable-v2
name: Expirable DELEGATECALL voucher — fails after expiration (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, delegatecall, voucher, expiry, v2, phase6]
csv_ids: ["6.6"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a226578706972 61626c655f766f756368657222 2c22657870 69726573223a31 7d"
    comment: "request an expirable voucher with a past expiry time"
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_timeout: 120
---

## Description
CSV test 6.6 — Emit an expirable DELEGATECALL voucher with a past expiration
timestamp and verify the voucher is emitted but its execution reverts after
the expiry.

## Steps
1. Submit an input requesting an expirable DELEGATECALL voucher.
2. Verify voucher is emitted by the VM.
3. (Executing after expiry should revert.)

## Expected Behaviour
- Expirable voucher emitted with correct expiry timestamp.
- Execution after expiry date reverts on-chain.
