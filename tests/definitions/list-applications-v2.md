---
id: list-applications-v2
name: Application Registration (v2.x)
version: 1
min_node_major_version: 2
tags: [registration, core, smoke, v2]
release_introduced: v2.0.0
component: jsonrpc-api
priority: high
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_listApplications
    use_app_address: false
    expect_count: 1
---

## Description
Verifies that the v2.x node has the test application registered and the
JSON-RPC API correctly reports it via `cartesi_listApplications`.

## Steps
1. Call `cartesi_listApplications()` (no params) on the JSON-RPC API.
2. Assert the result contains at least one application entry.

## Expected Behaviour
The deployed test application appears in the application list.
If no applications are found, the node failed to register the app
or the JSON-RPC API is not reachable.

## Notes
`use_app_address: false` because `cartesi_listApplications` takes no params.
This is a connectivity and registration sanity check — run it first for v2.x.
