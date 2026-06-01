---
id: delegatecall-ordered-v2
name: Ordered DELEGATECALL vouchers A-after-B — sequence dependency (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, delegatecall, voucher, ordering, v2, phase6]
csv_ids: ["6.9"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 360
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a226f72 64657265645f766f756368657273222c226d6f6465223a22 425f6669727374 227d"
    comment: "emit ordered vouchers: B must execute before A"
  - type: voucher_v2
    mode: generate
    expect_count: 2
    poll_timeout: 120
---

## Description
CSV test 6.9 — Emit two ordered DELEGATECALL vouchers where voucher A depends
on voucher B having been executed first.

## Steps
1. Submit an input emitting two ordered DELEGATECALL vouchers.
2. Verify both vouchers are emitted.
3. Executing A before B should revert; B then A should succeed.

## Expected Behaviour
- Both vouchers emitted with dependency encoded.
- Correct execution order enforced on-chain.
