---
id: jsonrpc-error-structure-v2
name: JSON-RPC error object has code/message/data fields (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, edge-cases, error-codes, v2, phase8]
csv_ids: ["8.34"]
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
    expect_error: true
    path: error.code
    value: -32601
---

## Description
CSV test 8.34 — Verify that error responses conform to the JSON-RPC 2.0 spec
with `code`, `message`, and optionally `data` fields.

## Steps
1. Trigger a known error (METHOD_NOT_FOUND) by calling a non-existent method.
2. Verify the `error` object contains `code` == -32601 and `message` is a string.

## Expected Behaviour
- `error.code` is an integer matching the expected error type.
- `error.message` is a non-empty string.
- Response does not include `result` alongside `error`.
