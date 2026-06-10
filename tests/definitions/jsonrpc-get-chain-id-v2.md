---
id: jsonrpc-get-chain-id-v2
ai_allowed: true
name: cartesi_getChainId returns correct chain ID (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, node-info, v2, phase8]
csv_ids: ["8.1"]
release_introduced: v2.0.0
component: jsonrpc
priority: high
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_getChainId
    use_app_address: false
    expect_has_field: "data"
---

## Description
CSV test 8.1 — Verify `cartesi_getChainId` returns the correct chain ID for the
running network (31337 for local Anvil).

## Steps
1. Call `cartesi_getChainId` with no parameters.
2. Assert the response contains a `chainId` field.

## Expected Behaviour
- Response is a valid JSON-RPC 2.0 success.
- `result.chainId` is present and equals the chain ID of the configured network.
