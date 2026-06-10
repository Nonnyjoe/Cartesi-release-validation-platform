---
id: graphql-inputs-query
ai_allowed: true
name: GraphQL Inputs Query (Multiple Inputs)
version: 1
tags: [graphql, core, indexer]
release_introduced: v1.4.0
component: graphql-server
priority: high
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node
  - graphql
inputs:
  payloads:
    - "0xaaaa"
    - "0xbbbb"
    - "0xcccc"
assertions:
  - type: chain_tx
    payload: "0xaaaa"
  - type: chain_tx
    payload: "0xbbbb"
  - type: chain_tx
    payload: "0xcccc"
  - type: graphql
    query: |
      { inputs { totalCount } }
    expect:
      path: inputs.totalCount
      value: 3
  - type: http_status
    endpoint: /graphql
    expect: 200
---

## Description
Verifies that the GraphQL indexer correctly tracks multiple sequential inputs and
reports the correct total count.

## Steps
1. Send three advance-state inputs: `0xaaaa`, `0xbbbb`, `0xcccc`.
2. Query `inputs.totalCount` — should be exactly 3.
3. Verify the GraphQL HTTP endpoint itself is reachable (returns 200 on GET).

## Expected Behaviour
After three inputs, `totalCount` returns 3. The order of indexing is preserved.

## Notes
Tests the indexer pipeline from InputBox event → dispatcher → GraphQL server.
If the count is wrong, the issue is likely in the indexer or event listener.
