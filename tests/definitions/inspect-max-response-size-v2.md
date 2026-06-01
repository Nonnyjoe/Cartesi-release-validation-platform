---
id: inspect-max-response-size-v2
name: Inspect at max response size boundary (2MB) (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, limits, edge-case, v2, phase5]
csv_ids: ["5.16"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: inspect_query
    payload: "0x7b22616374696f6e223a226c617267657265706f7274222c2273697a65223a22326d62227d"
    expect_status: 200
    comment: "request a 2MB inspect response (boundary test)"
---

## Description
CSV test 5.16 — Run an inspect query that requests the maximum response size
(2MB) and verify the node handles the boundary condition correctly.

## Steps
1. Send an inspect query requesting a 2MB response body.
2. Assert HTTP 200 is returned.
3. Verify the response payload is present and not truncated unexpectedly.

## Expected Behaviour
- 2MB inspect response is returned successfully.
- Node does not OOM or crash at the response size boundary.
