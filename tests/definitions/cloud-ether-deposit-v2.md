---
id: cloud-ether-deposit-v2
name: Send standard ETH deposit (cloud/sandbox) (v2.x)
version: 1
min_node_major_version: 2
tags: [input, deposit, ether, cloud, sandbox, v2, phase4]
csv_ids: ["4.2"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 90
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: ether
    amount: 1000000000000000000
  - type: notice_check
    min_count: 1
    poll_interval: 3
    poll_timeout: 60
---

## Description
CSV test 4.2 — Send a standard ETH deposit in cloud/sandbox mode and verify
ETH handling on live infrastructure.

## Steps
1. Deposit 1 ETH via EtherPortal.
2. Assert notice is generated.

## Expected Behaviour
- ETH deposit is processed on sandbox infrastructure.
- Notice with deposit details is emitted.
