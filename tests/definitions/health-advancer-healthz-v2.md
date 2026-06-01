---
id: health-advancer-healthz-v2
name: GET /readyz on advancer returns HTTP 200 (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, health, advancer, v2, phase13]
csv_ids: ["13.1"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 13.1 — Verify the advancer service's /readyz endpoint returns HTTP 200
when the service is healthy.

## Steps
1. Send GET /readyz to advancer (port 10002) via sandbox network.
2. Assert HTTP 200 response.

## Expected Behaviour
- /readyz returns HTTP 200 when advancer is running and healthy.
