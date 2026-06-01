---
id: voucher-erc20-withdrawal-v2
name: Generate ERC20 withdrawal voucher (v2.x)
version: 1
min_node_major_version: 2
tags: [output, voucher, erc20, withdrawal, v2, phase5]
csv_ids: ["5.7"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 300
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
    poll_timeout: 180
    trigger_payload: "withdraw_erc20"
---

## Description
CSV test 5.7 — Generate an ERC20 withdrawal voucher and verify it appears in
cartesi_listOutputs.

## Steps
1. Deposit 1,000,000 TestERC20 tokens.
2. Send a withdraw action.
3. Poll for ERC20 transfer voucher.

## Expected Behaviour
- `transfer(address,uint256)` voucher is generated.
- Voucher appears within 180s.
