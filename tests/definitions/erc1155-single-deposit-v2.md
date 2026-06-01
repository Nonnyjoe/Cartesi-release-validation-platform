---
id: erc1155-single-deposit-v2
name: ERC1155 single token deposit via portal (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, erc1155, assets, v2, phase3]
csv_ids: ["3.13"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc1155
    token_id: 1
    amount: 100
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 3.13 — Deposit a single ERC1155 token (token ID 1, amount 100) via
the ERC1155SinglePortal and verify the node indexes the resulting input.

## Steps
1. Deploy a test ERC1155 contract on Anvil.
2. Mint token ID 1 with amount 100 to the test sender.
3. Approve the ERC1155SinglePortal and call depositSingleERC1155Token.
4. Assert cartesi_listInputs returns at least 1 input.

## Expected Behaviour
- ERC1155 single deposit transaction succeeds.
- Input is indexed with correct token metadata.
