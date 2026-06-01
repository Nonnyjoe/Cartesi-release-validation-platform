---
id: erc721-with-data-v2
name: ERC721 Deposit with baseLayerData + execLayerData (v2.x)
version: 1
min_node_major_version: 2
tags: [portal, deposit, erc721, exec-layer-data, v2, phase3]
csv_ids: ["3.11"]
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
    token_id: 2
    exec_layer_data: "0xabcd"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
  - type: notice_check
    contains_text: "erc721_deposit"
    poll_interval: 3
    poll_timeout: 60
---

## Description
CSV test 3.11 — ERC721 deposit with baseLayerData and execLayerData fields.
Verifies the application receives the token and reflects extra data in a notice.

## Steps
1. Deploy TestERC721, mint token ID 42 to the sender.
2. Call `ERC721Portal.depositERC721Token(token, app, 42, 0x, 0xabcd)`.
3. Verify a notice with `erc721_deposit` is emitted.
