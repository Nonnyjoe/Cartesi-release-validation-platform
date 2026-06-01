---
id: cloud-erc1155-with-data-v2
name: ERC1155 deposit with baseLayerData + execLayerData on sandbox (v2.x)
version: 1
min_node_major_version: 2
tags: [cloud, portal, deposit, erc1155, exec-layer-data, v2, phase4]
csv_ids: ["4.10"]
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
    token_id: 5
    amount: 10
    base_layer_data: "0x"
    exec_layer_data: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 4.10 — Send an ERC1155 single deposit with baseLayerData and execLayerData
set (cloud-equivalent test on sandbox).

## Steps
1. Mint and deposit ERC1155 token ID 5, amount 10 with custom data fields.
2. Assert input indexed by node.

## Expected Behaviour
- Both data fields pass through to the VM correctly.
- Input available in cartesi_listInputs.
