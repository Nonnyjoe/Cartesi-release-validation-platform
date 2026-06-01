---
id: health-evm-reader-healthz-v2
name: GET /readyz on evm-reader returns HTTP 200 (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, health, evm-reader, v2, phase13]
csv_ids: ["13.4"]
release_introduced: v2.0.0
component: evm-reader
priority: high
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
CSV test 13.4 — Verify the evm-reader /readyz endpoint returns HTTP 200
when the service is healthy.

## Steps
1. Send GET /readyz to evm-reader (port 10001) via sandbox network.
2. Assert HTTP 200 response.

## Expected Behaviour
- /readyz returns HTTP 200 when evm-reader is running and connected to Anvil.
