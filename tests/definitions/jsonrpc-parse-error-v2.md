---
id: jsonrpc-parse-error-v2
name: Invalid JSON body returns -32700 PARSE_ERROR (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, edge-cases, error-codes, v2, phase8]
csv_ids: ["8.30"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: _raw
    use_app_address: false
    raw_body: "this is not json {"
    expect_error: true
---

## Description
CSV test 8.30 — Verify that sending an invalid JSON body to the JSON-RPC endpoint
returns error code -32700 (PARSE_ERROR).

## Steps
1. POST a non-JSON string body to the `/rpc` endpoint.
2. Assert the response error code is -32700.

## Expected Behaviour
- Response contains `error.code == -32700`.
- `error.message` is "Parse error" or similar.
