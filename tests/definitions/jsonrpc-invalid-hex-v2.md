---
id: jsonrpc-invalid-hex-v2
name: JSON-RPC query with invalid hex formats returns error (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, edge-cases, validation, v2, phase8]
csv_ids: ["8.15"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_getInput
    use_app_address: false
    params: ["not-a-valid-address", "0xZZZZZ"]
    expect_error: true
---

## Description
CSV test 8.15 — Verify that passing malformed hex strings to JSON-RPC methods
returns an appropriate error (INVALID_PARAMS or similar).

## Steps
1. Call `cartesi_getInput` with malformed hex string arguments.
2. Assert the response contains an error.

## Expected Behaviour
- Response contains `error` with code -32602 (INVALID_PARAMS) or similar.
- Node does not crash or return 500.
