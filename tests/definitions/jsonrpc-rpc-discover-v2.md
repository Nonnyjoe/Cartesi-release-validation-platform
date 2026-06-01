---
id: jsonrpc-rpc-discover-v2
name: rpc.discover returns OpenRPC spec (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, node-info, openrpc, v2, phase8]
csv_ids: ["8.21"]
release_introduced: v2.0.0
component: jsonrpc
priority: low
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: rpc.discover
    use_app_address: false
    expect_has_field: "openrpc"
---

## Description
CSV test 8.21 — Verify the `rpc.discover` meta-method returns a valid OpenRPC
specification document.

## Steps
1. Call `rpc.discover` with no parameters.
2. Assert the response contains an `openrpc` field.

## Expected Behaviour
- Response contains `result.openrpc` (e.g., "1.2.6").
- The document includes `info`, `methods`, and `servers` sections.
