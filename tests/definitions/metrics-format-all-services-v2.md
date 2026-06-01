---
id: metrics-format-all-services-v2
name: All node services healthy — readiness check across all services (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, health, v2, phase13]
csv_ids: ["13.12"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: health_check
    service: evm-reader
    path: /readyz
    expect_status: 200
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
  - type: health_check
    service: validator
    path: /readyz
    expect_status: 200
  - type: health_check
    service: claimer
    path: /readyz
    expect_status: 200
  - type: health_check
    service: jsonrpc
    path: /readyz
    expect_status: 200
---

## Description
CSV test 13.12 — Verify all Cartesi node services are ready and healthy.
Note: v2.x services expose /readyz (not /metrics) for health status.

## Steps
1. Check /readyz on all 5 services (evm-reader, advancer, validator, claimer, jsonrpc).
2. Validate each returns HTTP 200.

## Expected Behaviour
- All 5 services return HTTP 200 on /readyz.
- No service is unhealthy or crashing.
