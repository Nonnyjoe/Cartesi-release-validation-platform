---
id: jsonrpc-get-last-epoch-v2
name: cartesi_getLastAcceptedEpochIndex returns latest epoch (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, epochs, v2, phase8]
csv_ids: ["8.7"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_getLastAcceptedEpochIndex
    use_app_address: true
    expect_has_field: "data"
---

## Description
CSV test 8.7 — Verify `cartesi_getLastAcceptedEpochIndex` returns the latest
accepted epoch index.

## Steps
1. Call `cartesi_getLastAcceptedEpochIndex` with the app address.
2. Assert the response contains `epochIndex`.

## Expected Behaviour
- Response contains `result.epochIndex` as a non-negative integer.
