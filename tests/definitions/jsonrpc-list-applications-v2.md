---
id: jsonrpc-list-applications-v2
ai_allowed: true
name: cartesi_listApplications pagination (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, applications, pagination, v2, phase8]
csv_ids: ["8.3"]
release_introduced: v2.0.0
component: jsonrpc
priority: high
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_listApplications
    use_app_address: false
    expect_count: 1
---

## Description
CSV test 8.3 — Verify `cartesi_listApplications` returns at least one
application with correct pagination envelope.

## Steps
1. Call `cartesi_listApplications` with default parameters.
2. Assert at least one application is returned.

## Expected Behaviour
- Response contains `result.data` array with ≥1 application.
- Pagination metadata (`total`, `offset`, `limit`) is present.
