---
id: erc1155-exec-layer-data-v2
name: Send single ERC1155 with baseLayerData + execLayerData (v2.x)
version: 1
min_node_major_version: 2
tags: [input, deposit, erc1155, exec-layer-data, v2, phase3]
csv_ids: ["3.15"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc1155
    token_id: 1
    amount: 100
    exec_layer_data: "0xdeadbeef01"
  - type: notice_check
    min_count: 1
    contains_text: "exec_layer_data"
    poll_interval: 3
    poll_timeout: 60
---

## Description
CSV test 3.15 — Send a single ERC1155 deposit with both baseLayerData and
execLayerData fields populated and verify both are accessible in the VM.

## Steps
1. Deposit 100 units of token ID 1 with execLayerData = `0xdeadbeef01`.
2. Assert the application notice includes the execLayerData field.

## Expected Behaviour
- Application receives and surfaces the execLayerData in its notice payload.
