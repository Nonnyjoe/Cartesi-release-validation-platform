---
id: voucher-erc721-withdrawal-v2
name: Generate ERC721 withdrawal voucher (v2.x)
version: 1
min_node_major_version: 2
tags: [output, voucher, erc721, withdrawal, v2, phase5]
csv_ids: ["5.8"]
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
    token_type: erc721
    token_id: 4
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_interval: 3
    poll_timeout: 180
    trigger_payload: "withdraw_erc721"
---

## Description
CSV test 5.8 — Generate an ERC721 withdrawal voucher and verify it appears in
cartesi_listOutputs.

## Steps
1. Deposit ERC721 token ID 1.
2. Send a withdraw action.
3. Poll for safeTransferFrom voucher.

## Expected Behaviour
- `safeTransferFrom(address,address,uint256)` voucher is generated.
- Voucher appears within 180s.
