---
id: health-advancer-readyz-v2
name: GET /readyz on advancer returns HTTP 200 after DB connection ready (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, health, advancer, v2, phase13]
csv_ids: ["13.2"]
release_introduced: v2.0.0
component: advancer
priority: medium
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
CSV test 13.2 — Verify the advancer /readyz endpoint returns HTTP 200 only after
the database connection is established and ready.

## Steps
1. Send GET /readyz to advancer (port 10002).
2. Assert HTTP 200 response (DB connection is ready).

## Expected Behaviour
- /readyz returns HTTP 200 only when DB connection is ready.
