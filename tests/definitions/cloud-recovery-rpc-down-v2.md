---
id: cloud-recovery-rpc-down-v2
name: RPC provider failure — evm-reader handles endpoint down gracefully (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cloud, recovery, evm-reader, v2, phase9]
csv_ids: ["9.16"]
release_introduced: v2.0.0
component: evm-reader
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: service_restart
    service: anvil
    wait_healthy: true
    timeout: 90
    comment: "stopping and restarting anvil simulates RPC provider going down"
  - type: health_check
    service: evm-reader
    path: /readyz
    expect_status: 200
    poll_timeout: 120
---

## Description
CSV test 9.16 — Simulate an RPC provider failure by stopping Anvil (the local
chain node), and verify the evm-reader handles the outage gracefully.

## Steps
1. Stop the Anvil container (simulates RPC provider down).
2. Restart Anvil.
3. Assert evm-reader recovers and becomes healthy.

## Expected Behaviour
- evm-reader detects RPC failure and logs appropriate errors.
- No panic or crash; graceful retry/reconnect logic runs.
- evm-reader resumes normally once the RPC provider is back.
