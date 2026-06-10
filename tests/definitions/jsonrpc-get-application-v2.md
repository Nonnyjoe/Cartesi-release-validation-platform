---
id: jsonrpc-get-application-v2
ai_allowed: true
name: cartesi_getApplication fetch by hex address (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, applications, v2, phase8]
csv_ids: ["8.4"]
release_introduced: v2.0.0
component: jsonrpc
priority: high
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_getApplication
    use_app_address: true
---

## Description
CSV test 8.4 — Verify `cartesi_getApplication` fetches the application object
by its hex address.

## Steps
1. Call `cartesi_getApplication` with the deployed app address.
2. Assert the response contains the application object.

## Expected Behaviour
- Response contains the application's address, state, and epoch information.
