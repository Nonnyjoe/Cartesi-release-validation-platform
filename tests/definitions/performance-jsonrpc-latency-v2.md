---
id: performance-jsonrpc-latency-v2
name: JSON-RPC response latency under 50 concurrent queries (v2.x)
version: 1
min_node_major_version: 2
tags: [performance, latency, jsonrpc, v2, phase17]
csv_ids: ["17.5"]
release_introduced: v2.0.0
component: jsonrpc
priority: low
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_listApplications
    use_app_address: false
    stress_count: 50
---

## Description
CSV test 17.5 — Measure JSON-RPC response latency under 50 concurrent queries
and verify sub-500ms P99 under moderate load.

## Steps
1. Send 50 concurrent cartesi_listApplications requests.
2. Assert all succeed within timeout.

## Expected Behaviour
- All 50 requests succeed.
- P99 latency is under 500ms (verifiable via duration_ms in assertion results).
