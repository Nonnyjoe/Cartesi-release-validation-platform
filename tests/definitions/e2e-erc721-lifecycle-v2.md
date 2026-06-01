---
id: e2e-erc721-lifecycle-v2
name: E2E ERC721 deposit + withdrawal lifecycle (v2.x)
version: 1
min_node_major_version: 2
tags: [e2e, lifecycle, erc721, deposit, withdrawal, voucher, v2, phase7]
csv_ids: ["7.11"]
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
    token_type: erc721
    token_id: 5
  - type: voucher_v2
    mode: generate
    token_type: erc721
    expect_count: 1
    poll_interval: 3
    poll_timeout: 240
---

## Description
CSV test 7.11 — Full ERC721 deposit and withdrawal voucher lifecycle.

## Steps
1. Deposit ERC721 token ID 1 via ERC721Portal.
2. Send a JSON withdraw action for the deposited NFT.
3. Poll cartesi_listOutputs for an ERC721 safeTransferFrom voucher.

## Expected Behaviour
- Deposit registers the NFT with the student-tracker.
- Withdrawal generates a `safeTransferFrom(address,address,uint256)` voucher.
- Voucher appears in cartesi_listOutputs within 240s.
