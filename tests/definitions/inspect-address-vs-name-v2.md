---
id: inspect-address-vs-name-v2
name: Inspect via 0x address and name return identical result (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, http, v2, phase15]
csv_ids: ["15.7"]
release_introduced: v2.0.0
component: advancer
priority: low
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: inspect_query
    query: "status"
    expect_contains: "ok"
  - type: inspect_query
    query: "status"
    app_address_override: "student-tracker"
    expect_contains: "ok"
---

## Description
CSV test 15.7 — Verify that inspecting the application by 0x hex address and
by application name both return identical responses.

## Steps
1. POST to /inspect/{0x_address}/status.
2. POST to /inspect/{app_name}/status.
3. Assert both responses contain "ok".

## Expected Behaviour
- Both addressing modes return identical application state.
