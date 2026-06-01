---
id: delegatecall-targeted-voucher-v2
name: Targeted DELEGATECALL voucher — restricted to specific executors (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, delegatecall, voucher, whitelist, v2, phase6]
csv_ids: ["6.7"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2274617267657465645f766f756368657222 7d"
    comment: "request a whitelist-restricted DELEGATECALL voucher"
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_timeout: 120
---

## Description
CSV test 6.7 — Emit a targeted DELEGATECALL voucher that restricts execution
to a specific whitelisted executor address.

## Steps
1. Submit an input requesting a whitelist-restricted DELEGATECALL voucher.
2. Verify the voucher is emitted with the executor whitelist.
3. (Execution by a non-whitelisted address should revert.)

## Expected Behaviour
- Targeted voucher emitted with executor restriction in payload.
- Only whitelisted addresses can successfully execute the voucher on-chain.
