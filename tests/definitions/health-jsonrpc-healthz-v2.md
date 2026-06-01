---
id: health-jsonrpc-healthz-v2
name: GET /readyz on jsonrpc-api returns HTTP 200 (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, health, jsonrpc, v2, phase13]
csv_ids: ["13.10"]
release_introduced: v2.0.0
component: jsonrpc
priority: high
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: health_check
    service: jsonrpc
    path: /readyz
    expect_status: 200
---

## Description
CSV test 13.10 — Verify the jsonrpc-api /readyz endpoint returns HTTP 200.

## Steps
1. Send GET /readyz to jsonrpc-api (port 10005).
2. Assert HTTP 200.

## Expected Behaviour
- /readyz returns HTTP 200 when jsonrpc-api is running and healthy.
