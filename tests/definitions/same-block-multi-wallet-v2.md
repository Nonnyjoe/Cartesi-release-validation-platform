---
id: same-block-multi-wallet-v2
name: Same-block inputs from multiple wallets — verify correct ordering (v2.x)
version: 1
min_node_major_version: 2
tags: [input, ordering, multi-wallet, v2, phase3]
csv_ids: ["3.20"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a22696e707574312c77616c6c657431227d"
    comment: "input 1 from wallet 1"
  - type: chain_tx
    payload: "0x7b22616374696f6e223a22696e707574322c77616c6c657432227d"
    comment: "input 2 from wallet 2 (same block if mining is paused)"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 2
---

## Description
CSV test 3.20 — Send inputs from multiple wallets within the same block and
verify the application processes them in correct transaction-index order.

## Steps
1. Submit two inputs from different wallets (ideally in the same block).
2. Assert both inputs are indexed.
3. Assert ordering matches transaction index within the block.

## Expected Behaviour
- Both inputs are indexed.
- Input ordering matches the on-chain transaction order within the block.
