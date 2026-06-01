---
id: inspect-valid-v2
name: Valid inspect query — returns correct state (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, vm, core, v2, phase5]
csv_ids: ["5.13"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: inspect_query
    query: "summary"
    expect_json_field: "route"
    expect_json_value: "summary"
---

## Description
CSV test 5.13 — Triggers a valid inspect query against the running application
and verifies the correct state is returned.

## Steps
1. POST to /inspect/{app}/summary.
2. Decode the report payload as JSON.
3. Assert `result.route == "summary"`.

## Expected Behaviour
- Inspect returns HTTP 200.
- Decoded payload is valid JSON with `route: "summary"`.
