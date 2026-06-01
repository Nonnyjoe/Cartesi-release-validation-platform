---
id: cloud-eth-exec-layer-data-v2
name: ETH deposit with execLayerData on sandbox (v2.x)
version: 1
min_node_major_version: 2
tags: [cloud, portal, deposit, ether, exec-layer-data, v2, phase4]
csv_ids: ["4.3"]
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
    exec_layer_data: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 4.3 — Send an ETH deposit with custom execLayerData and verify the
data field is parsed correctly by the application (cloud-equivalent test on
sandbox infrastructure).

## Steps
1. Call EtherPortal.depositEther with execLayerData set to a JSON ping payload.
2. Assert input is indexed with the exec layer data present.

## Expected Behaviour
- ETH deposit succeeds with custom exec layer data.
- Input indexed with exec layer data available to the application.
