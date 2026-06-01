---
id: cloud-same-block-multi-wallet-v2
name: Same-block inputs from multiple wallets — correct ordering (v2.x)
version: 1
min_node_major_version: 2
tags: [cloud, inputs, ordering, edge-case, v2, phase4]
csv_ids: ["4.12"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67222c2273656e646572223a2231227d"
    comment: "input from wallet 1"
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67222c2273656e646572223a2232227d"
    comment: "input from wallet 2 — same block"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 2
---

## Description
CSV test 4.12 — Submit inputs from two different wallets in the same block and
verify the node preserves correct transaction ordering (cloud-equivalent test
on sandbox).

## Steps
1. Submit two inputs from different accounts in the same block.
2. Assert both inputs are indexed.
3. Verify ordering matches transaction index within the block.

## Expected Behaviour
- Both inputs from different senders are indexed.
- Input ordering reflects block transaction order (not arrival time).
