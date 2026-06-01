---
id: erc20-deposit-exec-layer-v2
name: ERC20 Deposit with execLayerData (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, erc20, exec-layer-data, v2, phase3]
csv_ids: ["3.8"]
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
    amount: 500000
    exec_layer_data: "0xcafe1234"
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
CSV test 3.8 — ERC20 deposit that includes a custom `execLayerData` field.
Verifies the application parses and echoes it in the deposit notice.

## Steps
1. Deploy test ERC20, mint 500,000 tokens, approve ERC20Portal.
2. Call `depositERC20Tokens(token, app, 500000, execLayerData=0xcafe1234)`.
3. Assert notice contains `exec_layer_data`.

## Expected Behaviour
- Deposit transaction succeeds.
- Notice payload includes `"exec_layer_data":"0xcafe1234"`.
