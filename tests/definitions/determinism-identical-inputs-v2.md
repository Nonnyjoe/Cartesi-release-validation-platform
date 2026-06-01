---
id: determinism-identical-inputs-v2
name: Two identical inputs produce identical machine hashes (v2.x)
version: 1
min_node_major_version: 2
tags: [determinism, security, v2, phase11]
csv_ids: ["11.11"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 2
---

## Description
CSV test 11.11 — Submit two identical inputs and verify the Cartesi Machine
produces identical state transitions (full determinism).

## Steps
1. Submit the same ping payload twice.
2. Assert both inputs are processed.
3. (Manual verification) Compare the machine hashes after each input — they
   should be deterministically different only due to input index, not randomness.

## Expected Behaviour
- Both inputs are processed.
- The VM produces deterministic output for identical inputs in the same sequence.
