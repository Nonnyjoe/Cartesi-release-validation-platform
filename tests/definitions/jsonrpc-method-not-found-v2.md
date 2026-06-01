---
id: jsonrpc-method-not-found-v2
name: Non-existent JSON-RPC method returns -32601 (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, edge-cases, error-codes, v2, phase8]
csv_ids: ["8.31"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_nonExistentMethod
    use_app_address: false
    expect_error_code: -32601
---

## Description
CSV test 8.31 — Verify that calling a non-existent JSON-RPC method returns
error code -32601 (METHOD_NOT_FOUND).

## Steps
1. Call `cartesi_nonExistentMethod` with no parameters.
2. Assert the response error code is -32601.

## Expected Behaviour
- Response contains `error.code == -32601`.
- `error.message` is "Method not found" or similar.
