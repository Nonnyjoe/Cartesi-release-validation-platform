---
id: erc1155-malformed-metadata-v2
name: ERC1155 deposit with malformed metadata — handled gracefully (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, erc1155, error-handling, v2, phase3]
csv_ids: ["3.17"]
release_introduced: v2.0.0
component: advancer
priority: low
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc1155
    token_id: 99
    amount: 50
    base_layer_data: "0xdeadbeef"
    exec_layer_data: "0xffffffff"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 3.17 — Deposit an ERC1155 token with intentionally malformed metadata
and verify the node handles it without crashing.

## Steps
1. Deposit ERC1155 token ID 99 with random hex baseLayerData + execLayerData.
2. Assert input is indexed by the node.

## Expected Behaviour
- Portal deposit succeeds despite corrupt metadata.
- Input indexed without crashing the node.
