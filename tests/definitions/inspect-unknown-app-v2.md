---
id: inspect-unknown-app-v2
name: POST /inspect for unknown application returns 404 (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, http, edge-cases, v2, phase15]
csv_ids: ["15.5"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: inspect_query
    query: "status"
    app_address_override: "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    expect_status: 404
---

## Description
CSV test 15.5 — POST /inspect to an unknown application address and verify a
404 or application-not-found error is returned.

## Steps
1. POST to /inspect/{unknown_address}/status.
2. Assert response is HTTP 404.

## Expected Behaviour
- HTTP 404 when the application is not registered with the node.
- No crash or 500 error.
