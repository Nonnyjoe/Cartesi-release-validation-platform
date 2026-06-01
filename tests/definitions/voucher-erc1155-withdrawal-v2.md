---
id: voucher-erc1155-withdrawal-v2
name: Generate ERC1155 single withdrawal voucher (v2.x)
version: 1
min_node_major_version: 2
tags: [output, voucher, erc1155, withdrawal, v2, phase5]
csv_ids: ["5.9"]
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
    token_type: erc1155
    token_id: 1
    amount: 100
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_interval: 3
    poll_timeout: 180
    trigger_payload: "withdraw_erc1155"
---

## Description
CSV test 5.9 — Generate an ERC1155 single withdrawal voucher and verify it
appears in cartesi_listOutputs.

## Steps
1. Deposit 100 units of ERC1155 token ID 1.
2. Send a withdraw action.
3. Poll for safeTransferFrom voucher.

## Expected Behaviour
- `safeTransferFrom(address,address,uint256,uint256,bytes)` voucher is generated.
- Voucher appears within 180s.
