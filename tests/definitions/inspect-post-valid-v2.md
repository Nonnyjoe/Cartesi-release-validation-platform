---
id: inspect-post-valid-v2
name: POST /inspect/{app} with valid payload returns correct state (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, http, v2, phase15]
csv_ids: ["15.1"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: inspect_query
    query: "status"
    method: POST
    expect_contains: "ok"
---

## Description
CSV test 15.1 — POST to /inspect/{app}/status with a valid payload and verify
the correct application state is returned via HTTP.

## Steps
1. POST to /inspect/{app_address}/status.
2. Assert the response body contains "ok".

## Expected Behaviour
- HTTP 200 response.
- Response body contains the application's current status.
