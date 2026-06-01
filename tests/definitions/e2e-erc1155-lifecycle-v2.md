---
id: e2e-erc1155-lifecycle-v2
name: E2E ERC1155 single deposit + withdrawal lifecycle (v2.x)
version: 1
min_node_major_version: 2
tags: [e2e, lifecycle, erc1155, deposit, withdrawal, voucher, v2, phase7]
csv_ids: ["7.12"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 420
requires:
  - anvil
  - cartesi-node-v2
  - claimer
assertions:
  - type: portal_deposit
    token_type: erc1155
    token_id: 1
    amount: 100
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_interval: 3
    poll_timeout: 240
    trigger_payload: "withdraw_erc1155"
---

## Description
CSV test 7.12 — Full ERC1155 single-token deposit and withdrawal lifecycle.

## Steps
1. Deposit 100 units of ERC1155 token ID 1 via ERC1155SinglePortal.
2. Send a JSON withdraw action for the deposited tokens.
3. Poll cartesi_listOutputs for an ERC1155 safeTransferFrom voucher.

## Expected Behaviour
- Deposit registers the ERC1155 balance with the student-tracker.
- Withdrawal generates a `safeTransferFrom(address,address,uint256,uint256,bytes)` voucher.
- Voucher appears in cartesi_listOutputs within 240s.
