---
id: erc1155-deposit-v2
name: ERC1155 Single Portal Deposit (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, erc1155, assets, v2]
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
Deploys a minimal ERC1155 test token on the sandbox Anvil, mints 100 units of
token ID=1 to Anvil account #0, grants `setApprovalForAll` to the
ERC1155SinglePortal, then calls `depositSingleERC1155Token`.  Verifies the
Cartesi node indexes the resulting input.

## Steps
1. Spawn a Foundry container in the Anvil network namespace.
2. Deploy `TestERC1155.sol` via `forge create`, mint 100x token ID=1 to the sender.
3. `setApprovalForAll(ERC1155Portal, true)` then call
   `depositSingleERC1155Token(token, app, 1, 100, 0x, 0x)`.
4. Poll `cartesi_listInputs(app_address)` and assert at least 1 input is present.

## Expected Behaviour
- All `cast send` transactions succeed.
- The node's JSON-RPC API returns ≥1 inputs after the deposit.

## Notes
Uses `ghcr.io/foundry-rs/foundry:latest`.  ERC1155 batch deposits are not tested
here; only single-token deposits via `ERC1155SinglePortal`.
