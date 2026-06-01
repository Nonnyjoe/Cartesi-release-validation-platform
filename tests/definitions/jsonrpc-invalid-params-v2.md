---
id: jsonrpc-invalid-params-v2
name: Decimal integer where hex required returns -32602 (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, edge-cases, error-codes, v2, phase8]
csv_ids: ["8.33"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_getApplication
    use_app_address: false
    params: [12345]
    expect_error_code: -32602
---

## Description
CSV test 8.33 — Verify that passing a decimal integer where a hex string is
required returns error code -32602 (INVALID_PARAMS).

## Steps
1. Call `cartesi_getApplication` with a decimal integer (12345) instead of a hex address.
2. Assert the response error code is -32602.

## Expected Behaviour
- Response contains `error.code == -32602`.
