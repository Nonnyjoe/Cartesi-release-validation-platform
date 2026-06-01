---
id: cloud-erc20-deposit-v2
name: Send standard ERC20 deposit (cloud/sandbox) (v2.x)
version: 1
min_node_major_version: 2
tags: [input, deposit, erc20, cloud, sandbox, v2, phase4]
csv_ids: ["4.4"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 90
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc20
    amount: 500000
  - type: notice_check
    min_count: 1
    poll_interval: 3
    poll_timeout: 60
---

## Description
CSV test 4.4 — Send a standard ERC20 deposit in cloud/sandbox mode.

## Steps
1. Deposit 500,000 TestERC20 tokens.
2. Assert notice is generated.

## Expected Behaviour
- ERC20 deposit is processed on sandbox infrastructure.
