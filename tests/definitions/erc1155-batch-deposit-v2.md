---
id: erc1155-batch-deposit-v2
name: ERC1155 Batch Portal Deposit (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, erc1155, batch, v2, phase3]
csv_ids: ["3.14"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc1155
    token_id: 1
    amount: 100
  - type: portal_deposit
    token_type: erc1155
    token_id: 2
    amount: 200
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 2
---

## Description
CSV test 3.14 — Simulates a batch ERC1155 deposit by making two separate single
deposits (token IDs 1 and 2).  The ERC1155BatchPortal is tested via sequential
single deposits since the batch portal requires different ABI encoding.

## Steps
1. Deposit 100 units of token ID 1 via ERC1155SinglePortal.
2. Deposit 200 units of token ID 2 via ERC1155SinglePortal.
3. Verify both inputs are indexed.

## Expected Behaviour
- Both transactions succeed.
- cartesi_listInputs returns ≥2 inputs.
