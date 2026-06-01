---
id: erc721-deposit-v2
name: ERC721 Portal Deposit (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, erc721, nft, assets, v2]
csv_ids: ["3.9"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc721
    token_id: 1
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
Deploys a minimal ERC721 test token on the sandbox Anvil, mints token #1 to Anvil
account #0, grants `setApprovalForAll` to the ERC721Portal, then calls
`depositERC721Token`.  Verifies the Cartesi node indexes the resulting input.

## Steps
1. Spawn a Foundry container in the Anvil network namespace.
2. Deploy `TestERC721.sol` via `forge create`, mint token ID=1 to the sender.
3. `setApprovalForAll(ERC721Portal, true)` then call
   `depositERC721Token(token, app, 1, 0x, 0x)`.
4. Poll `cartesi_listInputs(app_address)` and assert at least 1 input is present.

## Expected Behaviour
- All `cast send` transactions succeed.
- The node's JSON-RPC API returns ≥1 inputs after the deposit.

## Notes
Uses `ghcr.io/foundry-rs/foundry:latest`.  The `safeTransferFrom` variant
required by the portal is implemented in the minimal Solidity contract embedded
in the executor.
