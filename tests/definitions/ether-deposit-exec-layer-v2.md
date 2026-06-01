---
id: ether-deposit-exec-layer-v2
name: Ether Deposit with execLayerData (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, ether, exec-layer-data, v2, phase3]
csv_ids: ["3.5"]
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
    amount: 500000000000000000
    exec_layer_data: "0xdeadbeef"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
  - type: notice_check
    contains_text: "exec_layer_data"
    poll_interval: 3
    poll_timeout: 60
---

## Description
CSV test 3.5 — Deposits ETH with a custom `execLayerData` field and verifies
the Cartesi application receives and reflects it in a notice.

## Steps
1. Call `EtherPortal.depositEther(app, execLayerData)` with 0.5 ETH and
   execLayerData=`0xdeadbeef`.
2. Assert the notice payload contains `"exec_layer_data"`.

## Expected Behaviour
- The deposit transaction succeeds.
- student-tracker emits a notice containing `exec_layer_data` field.
