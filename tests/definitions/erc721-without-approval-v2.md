---
id: erc721-without-approval-v2
name: Send ERC721 without prior approval — contract reverts (v2.x)
version: 1
min_node_major_version: 2
tags: [input, deposit, erc721, approval, revert, v2, phase3]
csv_ids: ["3.10"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x"
    comment: "Submit input to verify node handles transactions normally"
---

## Description
CSV test 3.10 — Attempt to deposit an ERC721 without prior `setApprovalForAll`
or `approve` and verify the contract reverts.

## Steps
1. Attempt ERC721 deposit without approval.
2. Assert the transaction reverts.
3. Assert no input is indexed (no event emitted on revert).

## Expected Behaviour
- `transferFrom` reverts with "not approved" or similar.
- No InputBox event is emitted.
- cartesi_listInputs count does not increase.
