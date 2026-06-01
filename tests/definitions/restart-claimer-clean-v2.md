---
id: restart-claimer-clean-v2
name: Restart claimer immediately after boot — claim tracking ready (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, clean-restart, claimer, standalone, v2, phase2]
csv_ids: ["2.3"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 120
group: restart
suite_ids: [restart]
requires:
  - cartesi-node-v2
assertions:
  - type: service_restart
    service: claimer
    verify_path: /readyz
    verify_timeout: 60
  - type: health_check
    service: claimer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 2.3 — Restart the claimer service immediately after a clean boot and
verify claim tracking is ready.

## Steps
1. Restart the claimer container.
2. Poll /healthz until it returns HTTP 200.
3. Assert claimer is healthy within 60s.

## Expected Behaviour
- Claimer restarts cleanly.
- /healthz returns 200 within 60s.
