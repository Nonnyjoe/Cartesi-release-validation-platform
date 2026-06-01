---
id: cloud-erc721-deposit-v2
name: Send standard ERC721 deposit (cloud/sandbox) (v2.x)
version: 1
min_node_major_version: 2
tags: [input, deposit, erc721, cloud, sandbox, v2, phase4]
csv_ids: ["4.6"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 90
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc721
    token_id: 1
  - type: notice_check
    min_count: 1
    poll_interval: 3
    poll_timeout: 60
---

## Description
CSV test 4.6 — Send a standard ERC721 deposit in cloud/sandbox mode.

## Steps
1. Deposit ERC721 token ID 1.
2. Assert notice is generated.

## Expected Behaviour
- ERC721 deposit is processed on sandbox infrastructure.
