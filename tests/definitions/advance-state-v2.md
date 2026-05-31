---
id: advance-state-v2
name: Advance State Input (v2.x)
version: 1
min_node_major_version: 2
tags: [advance-state, core, smoke, v2]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0xdeadbeef"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
  - type: log_contains
    component: node
    pattern: "advance"
---

## Description
Core smoke test for v2.x: sends a raw hex input via the InputBox contract and
verifies the v2.x JSON-RPC API indexes it correctly.

## Steps
1. Submit payload `0xdeadbeef` to the InputBox contract via `eth_sendTransaction` on Anvil.
2. Call `cartesi_listInputs(app_address)` and assert at least 1 input is returned.
3. Scan the advancer logs to confirm it processed the input.

## Expected Behaviour
- The chain_tx succeeds (receipt status=1).
- `cartesi_listInputs` returns ≥1 items.
- Advancer logs contain "advance".

## Notes
v2.x has no GraphQL API — use `json_rpc` assertions instead.
`chain_tx` submits via InputBox.addInput() ABI-encoded call on the v2.x devnet.
