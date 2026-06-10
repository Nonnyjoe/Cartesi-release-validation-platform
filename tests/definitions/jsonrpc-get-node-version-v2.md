---
id: jsonrpc-get-node-version-v2
ai_allowed: true
name: cartesi_getNodeVersion returns version string (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, node-info, v2, phase8]
csv_ids: ["8.2"]
release_introduced: v2.0.0
component: jsonrpc
priority: high
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_getNodeVersion
    use_app_address: false
    expect_has_field: "data"
---

## Description
CSV test 8.2 — Verify `cartesi_getNodeVersion` returns a version string that
matches the deployed CLI/node version.

## Steps
1. Call `cartesi_getNodeVersion` with no parameters.
2. Assert the response contains a `version` field.

## Expected Behaviour
- Response contains `result.version` as a semver string (e.g., "2.0.0").
