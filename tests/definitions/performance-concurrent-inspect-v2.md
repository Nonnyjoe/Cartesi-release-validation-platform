---
id: performance-concurrent-inspect-v2
name: 50 concurrent inspect requests — all return correct responses (v2.x)
version: 1
min_node_major_version: 2
tags: [performance, concurrency, inspect, v2, phase17]
csv_ids: ["17.3"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: inspect_query
    query: "status"
    concurrent: 50
    expect_contains: "ok"
---

## Description
CSV test 17.3 — Send 50 concurrent inspect requests and verify all return
correct responses without crashes.

## Steps
1. Send 50 concurrent POST /inspect/{app}/status requests.
2. Assert all 50 return HTTP 200 with "ok" in the response.

## Expected Behaviour
- All 50 concurrent inspect requests succeed.
- No crashes, timeouts, or incorrect responses.
