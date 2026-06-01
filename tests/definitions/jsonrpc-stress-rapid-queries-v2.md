---
id: jsonrpc-stress-rapid-queries-v2
name: JSON-RPC 50+ rapid-fire queries stability test (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, stress, stability, v2, phase8]
csv_ids: ["8.20"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_listApplications
    use_app_address: false
    stress_count: 50
---

## Description
CSV test 8.20 — Verify the JSON-RPC API remains stable under 50 concurrent
rapid-fire queries.

## Steps
1. Send 50 concurrent `cartesi_listApplications` requests.
2. Assert all 50 requests succeed without HTTP errors or exceptions.

## Expected Behaviour
- All 50 requests return HTTP 200 with valid JSON-RPC responses.
- No connection errors, timeouts, or panics in the node.
