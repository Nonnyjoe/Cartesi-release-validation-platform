---
id: jsonrpc-out-of-bounds-v2
name: JSON-RPC query non-existent index returns error (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, edge-cases, v2, phase8]
csv_ids: ["8.16"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_getInput
    use_app_address: true
    params: [999999]
    expect_error: true
---

## Description
CSV test 8.16 — Verify that querying a non-existent index returns a proper
error response (not a crash or 500).

## Steps
1. Call `cartesi_getInput` with index 999999 (far beyond any existing input).
2. Assert the response contains an error.

## Expected Behaviour
- Response contains `error` indicating the input was not found.
- HTTP status is 200 (JSON-RPC level error, not HTTP error).
