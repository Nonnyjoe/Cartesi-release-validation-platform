---
id: ether-deposit-zero-v2
name: Send 0 ETH deposit boundary condition (v2.x)
version: 1
min_node_major_version: 2
tags: [input, deposit, ether, boundary, v2, phase3]
csv_ids: ["3.4"]
release_introduced: v2.0.0
component: advancer
priority: low
timeout_seconds: 90
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: ether
    amount: 0
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 3.4 — Send a 0 ETH deposit via EtherPortal and verify the application
handles the zero-value deposit correctly.

## Steps
1. Deposit 0 ETH via EtherPortal.
2. Assert the input is indexed.

## Expected Behaviour
- 0 ETH deposit is accepted by the portal contract.
- Application receives the deposit and records 0 balance change.
