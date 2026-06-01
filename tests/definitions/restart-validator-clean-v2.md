---
id: restart-validator-clean-v2
name: Restart validator immediately after boot — validation logic ready (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, clean-restart, validator, standalone, v2, phase2]
csv_ids: ["2.5"]
release_introduced: v2.0.0
component: validator
priority: high
timeout_seconds: 120
group: restart
suite_ids: [restart]
requires:
  - cartesi-node-v2
assertions:
  - type: service_restart
    service: validator
    verify_path: /readyz
    verify_timeout: 60
  - type: health_check
    service: validator
    path: /readyz
    expect_status: 200
---

## Description
CSV test 2.5 — Restart the validator service immediately after a clean boot and
verify validation logic is ready.

## Steps
1. Restart the validator container.
2. Poll /healthz until it returns HTTP 200.
3. Assert validator is healthy within 60s.

## Expected Behaviour
- Validator restarts cleanly.
- /healthz returns 200 within 60s.
