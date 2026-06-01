---
id: restart-advancer-clean-v2
name: Restart advancer immediately after boot — stable idle state (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, clean-restart, advancer, standalone, v2, phase2]
csv_ids: ["2.1"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 120
group: restart
suite_ids: [restart]
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: service_restart
    service: advancer
    verify_path: /readyz
    verify_timeout: 60
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 2.1 — Restart the advancer service immediately after a clean boot and
verify it returns to a stable idle state.

## Steps
1. Restart the advancer container.
2. Poll /healthz until it returns HTTP 200.
3. Assert the advancer is healthy within 60s.

## Expected Behaviour
- Advancer restarts cleanly with no panics.
- /healthz returns 200 within 60 seconds.
