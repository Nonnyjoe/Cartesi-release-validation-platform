---
id: generic-malformed-v2
name: Generic Input (v2.x) — malformed/empty payload
version: 1
min_node_major_version: 2
tags: [input, generic, error-handling, v2, phase3]
csv_ids: ["3.2"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 3.2 — Sends an empty payload to the InputBox.  The node should still
index it (the InputBox accepts any payload); the application will reject it and
emit a report, but the input itself is valid from the node perspective.

## Steps
1. Submit empty payload `0x` via InputBox.addInput.
2. Verify the node indexes the input (advancer records it even if app rejects).

## Expected Behaviour
- chain_tx succeeds (receipt status=1).
- cartesi_listInputs shows ≥1 input (node perspective — app may reject).
