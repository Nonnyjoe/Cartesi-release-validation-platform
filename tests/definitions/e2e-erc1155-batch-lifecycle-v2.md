---
id: e2e-erc1155-batch-lifecycle-v2
name: E2E ERC1155 batch deposit + withdrawal lifecycle (v2.x)
version: 1
min_node_major_version: 2
tags: [e2e, lifecycle, erc1155, batch, deposit, withdrawal, voucher, v2, phase7]
csv_ids: ["7.13"]
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
    token_type: erc1155_batch
    token_ids: [1, 2, 3]
    amounts: [100, 200, 50]
  - type: voucher_v2
    mode: generate
    token_type: erc1155
    expect_count: 1
    poll_interval: 3
    poll_timeout: 240
---

## Description
CSV test 7.13 — Full ERC1155 batch deposit and withdrawal lifecycle.

## Steps
1. Batch deposit ERC1155 tokens (IDs 1,2,3 with amounts 100,200,50) via ERC1155BatchPortal.
2. Send a JSON batch withdraw action.
3. Poll cartesi_listOutputs for an ERC1155 safeBatchTransferFrom voucher.

## Expected Behaviour
- Batch deposit registers multiple token balances with the student-tracker.
- Withdrawal generates a `safeBatchTransferFrom(address,address,uint256[],uint256[],bytes)` voucher.
- Voucher appears in cartesi_listOutputs within 240s.
