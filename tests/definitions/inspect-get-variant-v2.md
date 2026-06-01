---
id: inspect-get-variant-v2
name: GET /inspect/{app}?payload=... returns same result as POST (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, http, v2, phase15]
csv_ids: ["15.2"]
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
    expect_contains: "ok"
---

## Description
CSV test 15.2 — Verify the GET variant of /inspect returns the same result as
POST for identical payloads.

## Steps
1. GET /inspect/{app_address}/status.
2. Assert the response matches what POST returns.

## Expected Behaviour
- HTTP 200 response.
- Identical application state returned as POST variant.
