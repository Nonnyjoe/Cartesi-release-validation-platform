---
id: voucher-erc1155-batch-withdrawal-v2
name: Generate ERC1155 batch withdrawal voucher (v2.x)
version: 1
min_node_major_version: 2
tags: [output, voucher, erc1155, batch, withdrawal, v2, phase5]
csv_ids: ["5.10"]
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
    token_type: erc1155_batch
    token_ids: [1, 2]
    amounts: [100, 200]
  - type: voucher_v2
    mode: generate
    token_type: erc1155
    expect_count: 1
    poll_interval: 3
    poll_timeout: 180
---

## Description
CSV test 5.10 — Generate an ERC1155 batch withdrawal voucher and verify it
appears in cartesi_listOutputs.

## Steps
1. Batch deposit ERC1155 tokens [1, 2].
2. Send a batch withdraw action.
3. Poll for safeBatchTransferFrom voucher.

## Expected Behaviour
- `safeBatchTransferFrom(address,address,uint256[],uint256[],bytes)` voucher is generated.
- Voucher appears within 180s.
