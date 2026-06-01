---
id: execute-voucher-valid-v2
name: Execute valid voucher L2-to-L1 finalization (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, voucher, execute, v2, phase7]
csv_ids: ["7.4"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: voucher_v2
    mode: execute
    expect_count: 1
    poll_timeout: 180
---

## Description
CSV test 7.4 — Deposit ERC20 tokens, trigger a withdrawal voucher, wait for
epoch claim, and execute the voucher on-chain (L2-to-L1 finalization).

## Steps
1. Deposit ERC20 tokens via ERC20Portal.
2. Submit a withdraw action to trigger voucher emission.
3. Wait for epoch to be claimed.
4. Call CartesiDApp.executeOutput with the Merkle proof.

## Expected Behaviour
- Voucher executes successfully on-chain (tx status=1).
- ERC20 tokens are transferred back to the wallet.
