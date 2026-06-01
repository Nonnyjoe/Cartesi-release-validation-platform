---
id: cloud-erc20-exec-layer-data-v2
name: ERC20 deposit with execLayerData on sandbox (v2.x)
version: 1
min_node_major_version: 2
tags: [cloud, portal, deposit, erc20, exec-layer-data, v2, phase4]
csv_ids: ["4.5"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc20
    amount: 500
    exec_layer_data: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 4.5 — Send an ERC20 deposit with custom execLayerData and verify it
is received and indexed correctly (cloud-equivalent test on sandbox).

## Steps
1. Mint and deposit ERC20 tokens with a JSON ping as execLayerData.
2. Assert input is indexed.

## Expected Behaviour
- ERC20 deposit includes execLayerData passed through to the VM.
- Input indexed and available via cartesi_listInputs.
