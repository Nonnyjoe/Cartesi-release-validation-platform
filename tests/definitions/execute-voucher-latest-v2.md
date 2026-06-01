---
id: execute-voucher-latest-v2
name: Execute voucher with block=latest (fast finalization mode) (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, voucher, execute, v2, phase7]
csv_ids: ["7.7"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_BLOCKCHAIN_FINALITY_OFFSET: "0"
assertions:
  - type: voucher_v2
    mode: execute
    expect_count: 1
    poll_timeout: 180
---

## Description
CSV test 7.7 — Execute a voucher using `--block latest` (fast mode) and verify
the execution succeeds using the latest block state.

## Steps
1. Trigger a voucher via deposit + withdraw.
2. Wait for epoch claim in fast mode (finality offset = 0).
3. Execute the voucher on-chain.

## Expected Behaviour
- Voucher executes successfully using the latest block state.
- No need to wait for finalized confirmation blocks.
