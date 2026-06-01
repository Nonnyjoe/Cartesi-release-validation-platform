---
id: health-advancer-metrics-v2
name: GET /metrics on advancer returns Prometheus text format (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, metrics, advancer, v2, phase13]
csv_ids: ["13.3"]
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
CSV test 13.3 — Verify the advancer /metrics endpoint returns valid
Prometheus text-format metrics.

## Steps
1. Send GET /metrics to advancer (port 10002).
2. Assert response contains valid Prometheus # HELP and # TYPE lines.

## Expected Behaviour
- /metrics returns HTTP 200 with Prometheus text format.
- At least one metric family with # HELP and # TYPE annotations.
