---
id: voucher-eth-withdrawal-v2
name: Generate ETH withdrawal voucher (v2.x)
version: 1
min_node_major_version: 2
tags: [output, voucher, ether, withdrawal, v2, phase5]
csv_ids: ["5.6"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 240
requires:
  - anvil
  - cartesi-node-v2
  - claimer
assertions:
  - type: portal_deposit
    token_type: ether
    amount: 1000000000000000000
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_interval: 3
    poll_timeout: 120
    trigger_payload: "withdraw_ether"
---

## Description
CSV test 5.6 — Generate an ETH withdrawal voucher and verify it appears in
cartesi_listOutputs.

## Steps
1. Deposit 1 ETH via EtherPortal.
2. Send a withdraw action.
3. Poll for withdrawal voucher.

## Expected Behaviour
- `withdrawEther(address,uint256)` voucher is generated.
- Voucher appears within 120s.
