---
id: health-validator-readyz-v2
name: GET /readyz on validator returns HTTP 200 after DB connection (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, health, validator, v2, phase13]
csv_ids: ["13.7"]
release_introduced: v2.0.0
component: validator
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: health_check
    service: validator
    path: /readyz
    expect_status: 200
---

## Description
CSV test 13.7 — Verify the validator /readyz endpoint returns HTTP 200 after
the database connection is ready.

## Steps
1. Send GET /readyz to validator (port 10003).
2. Assert HTTP 200.

## Expected Behaviour
- /readyz returns HTTP 200 only when DB connection is established.
