---
id: dirty-restart-claimer-v2
name: Restart claimer during active epoch — resumes claim generation (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, dirty-restart, claimer, standalone, persistence, v2, phase9]
csv_ids: ["9.3"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 240
group: dirty_restart
suite_ids: [dirty_restart]
requires:
  - anvil
  - cartesi-node-v2
  - claimer
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: service_restart
    service: claimer
    verify_path: /readyz
    verify_timeout: 90
  - type: health_check
    service: claimer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 9.3 — Restart the claimer during an active epoch to verify it resumes
claim generation from where it left off.

## Steps
1. Submit an input to start epoch activity.
2. Restart the claimer container.
3. Verify claimer recovers to healthy state.

## Expected Behaviour
- Claimer resumes claim tracking without submitting duplicate claims.
- /healthz returns 200 within 90s.
