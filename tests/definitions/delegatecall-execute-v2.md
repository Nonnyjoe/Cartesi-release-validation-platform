---
id: delegatecall-execute-v2
name: Execute DELEGATECALL voucher on-chain — logic runs from target contract (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, delegatecall, voucher, v2, phase6]
csv_ids: ["6.2"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2264656c65676174656361 6c6c5f766f756368657222 2c22737465707322 3a317d"
    comment: "request DELEGATECALL voucher emission"
  - type: voucher_v2
    mode: execute
    expect_count: 1
    poll_timeout: 240
---

## Description
CSV test 6.2 — Emit a DELEGATECALL voucher from the VM and execute it on-chain,
verifying the logic runs in the context of the target contract.

## Steps
1. Submit an input that emits a DELEGATECALL voucher.
2. Wait for epoch claim.
3. Execute the DELEGATECALL voucher via executeOutput.

## Expected Behaviour
- DELEGATECALL executes in the context of the target contract.
- Target contract's logic runs as if called from the CartesiDApp.
- Execution receipt returned successfully.
