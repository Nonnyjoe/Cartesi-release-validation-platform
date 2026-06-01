---
id: security-reentrancy-v2
name: Reentrancy attack during deposit — contract security (v2.x)
version: 1
min_node_major_version: 2
tags: [security, reentrancy, contracts, v2, phase11]
csv_ids: ["11.5"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x"
    comment: "submit an input to verify reentrancy protection does not affect normal transactions"
---

## Description
CSV test 11.5 — Attempt a reentrancy attack during an Ether deposit via a
malicious contract that calls depositEther recursively, and verify the portal
contract prevents it.

## Steps
1. Deploy a malicious contract that calls depositEther inside its receive().
2. Attempt the reentrancy attack transaction.
3. Assert the transaction reverts.

## Expected Behaviour
- Portal contracts are protected against reentrancy.
- Malicious reentrancy call reverts cleanly.
- No state corruption in the InputBox.
