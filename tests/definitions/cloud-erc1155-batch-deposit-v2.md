---
id: cloud-erc1155-batch-deposit-v2
name: Send batch ERC1155 deposit (cloud/sandbox) (v2.x)
version: 1
min_node_major_version: 2
tags: [input, deposit, erc1155, batch, cloud, sandbox, v2, phase4]
csv_ids: ["4.9"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 90
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: portal_deposit
    token_type: erc1155_batch
    token_ids: [1, 2]
    amounts: [100, 200]
  - type: notice_check
    min_count: 1
    poll_interval: 3
    poll_timeout: 60
---

## Description
CSV test 4.9 — Send a batch ERC1155 deposit in cloud/sandbox mode.

## Steps
1. Batch deposit ERC1155 tokens [1, 2] with amounts [100, 200].
2. Assert notice is generated.

## Expected Behaviour
- Batch ERC1155 deposit is processed on sandbox infrastructure.
