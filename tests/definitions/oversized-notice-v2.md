---
id: oversized-notice-v2
name: Oversized notice (>2MB) — limit or rejection handled (v2.x)
version: 1
min_node_major_version: 2
tags: [outputs, notice, edge-case, limits, v2, phase5]
csv_ids: ["5.3"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a226c617267656e6f74696365222c2273697a65223a22336d62227d"
    comment: "request to emit a 3MB notice — exceeds the 2MB limit"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
    comment: "input must be indexed even if notice is rejected"
---

## Description
CSV test 5.3 — Request the application to emit a notice larger than 2MB and
verify the VM handles it gracefully (either truncating or rejecting with an
error, not crashing).

## Steps
1. Submit an input instructing the app to emit a 3MB notice.
2. Assert the input is still processed.
3. Verify no crash or node panic occurs.

## Expected Behaviour
- VM handles oversized notice gracefully (reject or truncate).
- Node does not crash or panic.
- Input is still indexed and counted as processed.
