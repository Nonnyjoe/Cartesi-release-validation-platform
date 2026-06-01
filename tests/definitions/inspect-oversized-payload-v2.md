---
id: inspect-oversized-payload-v2
name: POST /inspect with payload exceeding 2MB returns 413 (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, limits, v2, phase15]
csv_ids: ["15.4"]
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
    comment: "Placeholder: oversized test needs dedicated large-payload generator"
---

## Description
CSV test 15.4 — POST /inspect with a payload exceeding the 2MB limit and
verify a 413 or appropriate error is returned without crashing the node.

Note: Full test requires the executor to generate a >2MB query string. This
definition serves as a placeholder; the test will be automated with a dedicated
oversized-payload assertion variant.

## Steps
1. POST /inspect with a payload exceeding 2MB.
2. Assert HTTP 413 (or 400) is returned.
3. Assert the node does not crash.

## Expected Behaviour
- HTTP 413 Payload Too Large (or 400) is returned.
- Node remains healthy after the oversized request.
