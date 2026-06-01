---
id: report-inspect-v2
name: Report during inspect (v2.x)
version: 1
min_node_major_version: 2
tags: [output, report, inspect, vm, v2, phase5]
csv_ids: ["5.12"]
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
CSV test 5.12 — Triggers an inspect query and verifies the application emits
a report as part of the inspect response.

The student-tracker emits a report containing its status JSON when queried
with the `status` route.

## Steps
1. POST to /inspect/{app}/status.
2. Verify the response contains a report with `"status":"ok"`.

## Expected Behaviour
- Inspect returns HTTP 200.
- Response report payload decodes to JSON containing `"status":"ok"`.
