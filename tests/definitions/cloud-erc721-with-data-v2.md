---
id: cloud-erc721-with-data-v2
name: ERC721 deposit with baseLayerData + execLayerData on sandbox (v2.x)
version: 1
min_node_major_version: 2
tags: [cloud, portal, deposit, erc721, exec-layer-data, v2, phase4]
csv_ids: ["4.7"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc721
    token_id: 10
    base_layer_data: "0x"
    exec_layer_data: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 4.7 — Send an ERC721 deposit with both baseLayerData and execLayerData
on sandbox infrastructure (cloud-equivalent test).

## Steps
1. Mint ERC721 token ID 10.
2. Deposit with baseLayerData and execLayerData set.
3. Assert input indexed.

## Expected Behaviour
- Both data fields are passed through to the VM correctly.
- Input indexed by the node.
