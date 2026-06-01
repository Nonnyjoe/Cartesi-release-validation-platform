---
id: health-evm-reader-readyz-v2
name: GET /readyz on evm-reader returns HTTP 200 after WS subscription active (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, health, evm-reader, v2, phase13]
csv_ids: ["13.5"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 30
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: health_check
    service: evm-reader
    path: /readyz
    expect_status: 200
---

## Description
CSV test 13.5 — Verify the evm-reader /readyz endpoint returns HTTP 200 only
after the WebSocket subscription to Anvil is active.

## Steps
1. Send GET /readyz to evm-reader (port 10001).
2. Assert HTTP 200 (WS subscription is active).

## Expected Behaviour
- /readyz returns HTTP 200 only when WS is connected and subscription is active.
