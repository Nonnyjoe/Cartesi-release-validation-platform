---
id: e2e-ether-lifecycle-v2
name: E2E ETH deposit + withdrawal lifecycle (v2.x)
version: 1
min_node_major_version: 2
tags: [e2e, lifecycle, ether, deposit, withdrawal, voucher, v2, phase7]
csv_ids: ["7.9"]
release_introduced: v2.0.0
component: claimer
priority: critical
timeout_seconds: 420
requires:
  - anvil
  - cartesi-node-v2
  - claimer
assertions:
  - type: portal_deposit
    token_type: ether
    amount: 1000000000000000000
  - type: chain_tx
    payload: '{"action":"withdraw","asset_type":"ether"}'
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_interval: 3
    poll_timeout: 120
---

## Description
CSV test 7.9 — Full ETH deposit + withdrawal voucher lifecycle.

## Steps
1. Deposit 1 ETH via EtherPortal (registers depositor as auto-student).
2. Send a JSON `{"action":"withdraw","asset_type":"ether","amount":"1000000000000000000"}` payload.
3. Poll cartesi_listOutputs until an ETH withdrawal voucher appears.

## Expected Behaviour
- EtherPortal deposit succeeds and the app records the ETH balance.
- Withdraw action generates a withdrawEther() voucher.
- cartesi_listOutputs returns ≥1 voucher.
