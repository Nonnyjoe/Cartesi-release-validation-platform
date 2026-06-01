---
id: e2e-erc20-lifecycle-v2
name: E2E ERC20 deposit + withdrawal lifecycle (v2.x)
version: 1
min_node_major_version: 2
tags: [e2e, lifecycle, erc20, deposit, withdrawal, voucher, v2, phase7]
csv_ids: ["7.10"]
release_introduced: v2.0.0
component: claimer
priority: critical
timeout_seconds: 420
requires:
  - anvil
  - cartesi-node-v2
  - claimer
assertions:
  - type: portal_deposit
    token_type: erc20
    amount: 1000000
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_interval: 3
    poll_timeout: 240
    trigger_payload: "withdraw_erc20"
---

## Description
CSV test 7.10 — Full ERC20 deposit and withdrawal voucher lifecycle.

## Steps
1. Deposit 1,000,000 TestERC20 tokens via ERC20Portal.
2. Send a JSON withdraw action for the deposited tokens.
3. Poll cartesi_listOutputs for an ERC20 transfer voucher.

## Expected Behaviour
- Deposit registers auto-student with 1,000,000 token balance.
- Withdrawal generates a `transfer(address,uint256)` voucher targeting the ERC20 token contract.
- Voucher appears in cartesi_listOutputs within 240s.
