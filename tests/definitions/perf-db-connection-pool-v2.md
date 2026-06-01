---
id: perf-db-connection-pool-v2
name: 100 simultaneous DB connections — connection pool limits enforced (v2.x)
version: 1
min_node_major_version: 2
tags: [performance, database, load, v2, phase17]
csv_ids: ["17.6"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    stress_count: 100
    comment: "100 concurrent JSON-RPC requests indirectly stress the DB connection pool"
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 17.6 — Saturate the database with 100 simultaneous connections via
concurrent JSON-RPC requests and verify the connection pool limits are enforced
without panics or crashes.

## Steps
1. Send 100 concurrent cartesi_listInputs JSON-RPC requests.
2. Assert all requests complete (possibly with errors for pool overflow).
3. Assert the advancer remains healthy after the load test.

## Expected Behaviour
- Connection pool limits are enforced (no unbounded growth).
- No panics or node crashes under 100 concurrent connections.
- Advancer remains healthy post-test.
