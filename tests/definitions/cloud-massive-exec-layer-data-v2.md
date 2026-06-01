---
id: cloud-massive-exec-layer-data-v2
name: ETH deposit with massive execLayerData tests gas limits on sandbox (v2.x)
version: 1
min_node_major_version: 2
tags: [cloud, portal, deposit, ether, edge-case, v2, phase4]
csv_ids: ["4.11"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: ether
    amount: 1000000000000000000
    exec_layer_data_size_bytes: 32768
    comment: "32 KB execLayerData to stress gas and VM extraction"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 4.11 — Send an ETH deposit with very large execLayerData (32 KB) on
sandbox to test gas limits and VM data extraction for cloud-equivalent workload.

## Steps
1. Generate 32 KB of execLayerData.
2. Deposit ETH with that data via EtherPortal.
3. Assert input is indexed by the node.

## Expected Behaviour
- Large execLayerData deposit succeeds within gas limits.
- Input indexed with full data available to the VM.
