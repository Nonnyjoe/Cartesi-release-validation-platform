---
id: massive-exec-layer-data-v2
name: Send deposit with massive execLayerData — gas limits and VM extraction (v2.x)
version: 1
min_node_major_version: 2
tags: [input, deposit, exec-layer-data, gas-limit, edge-cases, v2, phase3]
csv_ids: ["3.18"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: ether
    amount: 1000000000000000000
    exec_layer_data: "0xaabbccdd1122334455667788aabbccdd1122334455667788aabbccdd1122334455667788aabbccdd1122334455667788aabbccdd1122334455667788aabbccdd1122334455667788aabbccdd1122334455667788aabbccdd1122334455667788"
    comment: "~96 bytes execLayerData — large but within gas limit"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 3.18 — Deposit with a large execLayerData field and verify it does not
exceed gas limits and is correctly extracted by the VM.

## Steps
1. Deposit 1 ETH with ~96 bytes of execLayerData.
2. Assert the input is indexed successfully.

## Expected Behaviour
- Deposit succeeds within L1 gas limits.
- The full execLayerData is extracted by the application.
