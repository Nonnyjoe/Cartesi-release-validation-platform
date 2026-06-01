---
id: erc1155-batch-exec-layer-data-v2
name: Send batch ERC1155 with baseLayerData + execLayerData (v2.x)
version: 1
min_node_major_version: 2
tags: [input, deposit, erc1155, batch, exec-layer-data, v2, phase3]
csv_ids: ["3.16"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc1155_batch
    token_ids: [1, 2]
    amounts: [100, 200]
    exec_layer_data: "0xcafe0001"
  - type: notice_check
    min_count: 1
    contains_text: "exec_layer_data"
    poll_interval: 3
    poll_timeout: 60
---

## Description
CSV test 3.16 — Send a batch ERC1155 deposit with execLayerData and verify the
application surfaces it in the notice payload.

## Steps
1. Batch deposit token IDs [1, 2] with amounts [100, 200] + execLayerData = `0xcafe0001`.
2. Assert the application notice includes the execLayerData field.

## Expected Behaviour
- execLayerData from the batch deposit is accessible in the VM.
- Notice payload contains the extra data field.
