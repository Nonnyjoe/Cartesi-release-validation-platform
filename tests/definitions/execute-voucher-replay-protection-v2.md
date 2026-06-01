---
id: execute-voucher-replay-protection-v2
name: Execute same voucher twice — replay protection prevents double-spend (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, voucher, replay, security, v2, phase7]
csv_ids: ["7.5"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 360
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: voucher_v2
    mode: execute
    expect_count: 1
    poll_timeout: 180
  - type: health_check
    service: claimer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 7.5 — Execute a voucher once (succeeds), then attempt to execute the
same voucher a second time and verify the replay is rejected by the contract.

## Steps
1. Execute the voucher successfully (first call).
2. Attempt to call executeOutput again with the same proof.
3. Assert the second call reverts (replay protection).

## Expected Behaviour
- First voucher execution succeeds with tx status=1.
- Second execution attempt reverts (contract tracks executed outputs).
