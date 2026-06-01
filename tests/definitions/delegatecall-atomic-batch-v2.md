---
id: delegatecall-atomic-batch-v2
name: Atomic DELEGATECALL batch vouchers — all-or-nothing (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, delegatecall, voucher, batch, atomic, v2, phase6]
csv_ids: ["6.10"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 360
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2261746f6d69635f626174 6368222c22636f756e74223a 33 7d"
    comment: "emit 3 atomic batch DELEGATECALL vouchers"
  - type: voucher_v2
    mode: generate
    expect_count: 3
    poll_timeout: 120
---

## Description
CSV test 6.10 — Emit a batch of atomic DELEGATECALL vouchers where all must
succeed or the entire batch is reverted (all-or-nothing semantics).

## Steps
1. Submit an input emitting 3 atomic DELEGATECALL vouchers.
2. Verify all 3 vouchers appear in outputs.
3. Executing the batch atomically should succeed or fail together.

## Expected Behaviour
- All 3 vouchers emitted correctly.
- Atomic batch execution ensures all-or-nothing behavior.
