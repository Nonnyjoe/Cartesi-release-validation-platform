---
id: erc20-fee-on-transfer-v2
name: Send fee-on-transfer ERC20 deposit — precision test (v2.x)
version: 1
min_node_major_version: 2
tags: [input, deposit, erc20, fee-on-transfer, v2, phase3]
csv_ids: ["3.7"]
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
    amount: 1000000
    comment: "Standard TestERC20 does not have fees; test verifies amount precision"
  - type: notice_check
    min_count: 1
    poll_interval: 3
    poll_timeout: 60
---

## Description
CSV test 3.7 — Deposit a fee-on-transfer ERC20 token and verify the application
receives the post-fee amount (not the pre-fee transfer amount).

Note: This test uses the standard TestERC20 as a substitute; a fee-on-transfer
token must be deployed separately for full coverage.

## Steps
1. Deposit 1,000,000 tokens via ERC20Portal.
2. Assert notice is generated with the received amount.

## Expected Behaviour
- Application records the actual received amount (may differ from sent amount
  if a fee-on-transfer token is used).
