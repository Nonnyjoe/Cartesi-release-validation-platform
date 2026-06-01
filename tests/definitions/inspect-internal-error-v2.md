---
id: inspect-internal-error-v2
name: Inspect causing internal error bubbles up correctly (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, vm, error-handling, v2, phase5]
csv_ids: ["5.14"]
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
CSV test 5.14 — Send an inspect request that causes an internal application
error and verify the error bubbles up correctly via the HTTP response.

## Steps
1. POST to /inspect/{app}/trigger_error.
2. Assert HTTP 500 (or application-defined error) is returned.

## Expected Behaviour
- HTTP error status (500 or 4xx) returned.
- No node crash.
- Error response is well-formed.
