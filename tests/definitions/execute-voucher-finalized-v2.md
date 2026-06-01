---
id: execute-voucher-finalized-v2
name: Execute voucher with block=finalized (production mode) (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, voucher, execute, v2, phase7]
csv_ids: ["7.8"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 360
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: voucher_v2
    mode: execute
    expect_count: 1
    poll_timeout: 240
---

## Description
CSV test 7.8 — Execute a voucher using `--block finalized` (production mode)
and verify execution succeeds after full finality confirmation.

## Steps
1. Trigger a voucher via deposit + withdraw.
2. Wait for epoch to reach CLAIM_ACCEPTED with finalized block confirmation.
3. Execute the voucher on-chain.

## Expected Behaviour
- Voucher executes using finalized block state.
- Production finality ensures settled epoch before execution.
