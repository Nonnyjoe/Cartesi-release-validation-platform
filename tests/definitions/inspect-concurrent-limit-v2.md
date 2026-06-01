---
id: inspect-concurrent-limit-v2
name: Concurrent inspects up to execution-parameters limit (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, concurrent, v2, phase15]
csv_ids: ["15.6"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 90
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: inspect_query
    query: "status"
    concurrent: 10
    expect_contains: "ok"
---

## Description
CSV test 15.6 — Send concurrent inspect requests up to the configured
execution-parameters concurrency limit and verify all are handled.

## Steps
1. Send 10 concurrent POST /inspect/{app}/status requests.
2. Assert all return HTTP 200 with "ok".

## Expected Behaviour
- All concurrent requests up to the limit are handled correctly.
- Requests beyond the limit (if any) are queued, not dropped.
