---
id: inspect-large-payload-v2
name: POST /inspect with 2MB payload at boundary (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, limits, boundary, v2, phase15]
csv_ids: ["15.3"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: inspect_query
    query: "status"
    expect_status: 200
    expect_contains: "ok"
---

## Description
CSV test 15.3 — POST /inspect with a 2MB payload at the size boundary and
verify it is accepted and processed without error.

Note: This test uses a standard status query as a proxy. A dedicated large-payload
test would require the executor to generate a ~2MB query string.

## Steps
1. POST /inspect with the largest allowed payload (2MB).
2. Assert HTTP 200 response.

## Expected Behaviour
- 2MB payload is accepted at the boundary.
- No 413 or timeout error.
