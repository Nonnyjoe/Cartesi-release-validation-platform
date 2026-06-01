---
id: l1-reorg-v2
name: Simulate L1 chain reorganization — block rewinding handled (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, recovery, reorg, v2, phase9]
csv_ids: ["9.12"]
release_introduced: v2.0.0
component: evm-reader
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
  - type: log_contains
    service: evm-reader
    text: "reorg"
    timeout_seconds: 60
    comment: "evm-reader must detect and handle the chain reorganization"
---

## Description
CSV test 9.12 — Use Anvil's `anvil_mine` + revert to simulate a chain
reorganization and verify the evm-reader handles block rewinding correctly
without corrupting the input index.

## Setup
This test requires Anvil's reorg simulation capability (anvil_reorg or
manual snapshot+revert).

## Steps
1. Submit an input and confirm it's indexed.
2. Trigger an Anvil reorg (revert to a snapshot before the input).
3. Resubmit the input.
4. Assert evm-reader logs mention reorg handling.
5. Assert final input count is correct.

## Expected Behaviour
- evm-reader detects the chain reorganization.
- Reorged inputs are removed and re-indexed when re-mined.
- No duplicate inputs or state corruption.
