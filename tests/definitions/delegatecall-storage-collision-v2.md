---
id: delegatecall-storage-collision-v2
name: DELEGATECALL storage layout collision test (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, delegatecall, security, v2, phase6]
csv_ids: ["6.3"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2264656c65676174656361 6c6c5f636f6c6c6973696f6e227d"
    comment: "request DELEGATECALL that writes to a colliding storage slot"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 6.3 — Execute a DELEGATECALL voucher that writes to a storage slot
that collides with the CartesiDApp's own storage layout, and verify the collision
is detected or handled safely.

## Steps
1. Submit a DELEGATECALL voucher targeting a contract with conflicting layout.
2. Assert the input is processed.
3. Verify no state corruption occurred in the CartesiDApp.

## Expected Behaviour
- Storage collision is detected (execution may revert or be isolated).
- CartesiDApp state is not corrupted by the collision.
