---
id: generic-input-v2
ai_allowed: true
name: Generic Input (v2.x) — valid payload
version: 1
min_node_major_version: 2
tags: [input, generic, core, v2, phase3]
csv_ids: ["3.1"]
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
---

## Description
CSV test 3.1 — Sends a valid generic hex payload to the InputBox and verifies
the advancer indexes it.

## Steps
1. Submit `0xdeadbeef` via InputBox.addInput.
2. Poll `cartesi_listInputs(app)` and assert ≥1 input indexed.

## Expected Behaviour
- chain_tx receipt status=1.
- At least 1 input visible in JSON-RPC.
