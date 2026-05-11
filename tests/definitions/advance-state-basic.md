---
id: advance-state-basic
name: Basic Advance State Input
version: 1
tags: [advance-state, core, smoke]
release_introduced: v1.4.0
component: dispatcher
priority: high
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node
  - graphql
inputs:
  payload: "0xdeadbeef"
  chain_id: 31337
assertions:
  - type: chain_tx
    payload: "0xdeadbeef"
    app_address: "0x0000000000000000000000000000000000000001"
  - type: graphql
    query: |
      { inputs { edges { node { index payload } } } }
    expect:
      path: inputs.edges[0].node.payload
      value: "0xdeadbeef"
  - type: log_contains
    component: node
    pattern: "input accepted"
  - type: http_status
    endpoint: /healthz
    expect: 200
---

## Description
Tests the most fundamental operation of the Cartesi rollups node: accepting an
advance-state input through the InputBox contract and correctly indexing it.

## Steps
1. Send a raw hex payload `0xdeadbeef` to the InputBox contract via the HTTP bridge.
2. Query the GraphQL API to confirm the input appears at index 0 with the correct payload.
3. Scan the node logs to confirm the dispatcher logged "input accepted".
4. Health-check the node HTTP endpoint.

## Expected Behaviour
- The chain_tx call returns 2xx.
- GraphQL returns the input at index 0 with payload matching `0xdeadbeef`.
- Logs contain "input accepted".
- `/healthz` returns 200.

## Notes
This is the canonical smoke test — if this fails, all other tests will likely fail too.
Run this first in any test suite.
