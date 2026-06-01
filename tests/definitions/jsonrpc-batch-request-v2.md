---
id: jsonrpc-batch-request-v2
name: JSON-RPC 2.0 batch request array handling (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, edge-cases, batch, v2, phase8]
csv_ids: ["8.32"]
release_introduced: v2.0.0
component: jsonrpc
priority: low
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: _raw
    use_app_address: false
    raw_body: '[{"jsonrpc":"2.0","method":"cartesi_listApplications","params":[],"id":1}]'
    expect_error: true
---

## Description
CSV test 8.32 — Verify the node handles (or rejects with a spec-compliant error)
a JSON-RPC 2.0 batch request array.

## Steps
1. POST a JSON array containing a single valid JSON-RPC request.
2. Assert the response is either a valid batch response or a spec-compliant error.

## Expected Behaviour
- If batch is unsupported: `error.code` is defined (e.g., -32600 INVALID_REQUEST).
- If batch is supported: response is a JSON array with one result.
- Node does not crash.
