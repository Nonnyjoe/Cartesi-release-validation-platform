---
id: health-claimer-healthz-v2
name: GET /readyz on claimer returns HTTP 200 (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, health, claimer, v2, phase13]
csv_ids: ["13.8"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: health_check
    service: claimer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 13.8 — Verify the claimer /readyz endpoint returns HTTP 200.

## Steps
1. Send GET /readyz to claimer (port 10004).
2. Assert HTTP 200.

## Expected Behaviour
- /readyz returns HTTP 200 when claimer is running and healthy.
