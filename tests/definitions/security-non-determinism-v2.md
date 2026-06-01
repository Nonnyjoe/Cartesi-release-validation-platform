---
id: security-non-determinism-v2
name: Call Date.now() inside VM — non-deterministic ops handled (v2.x)
version: 1
min_node_major_version: 2
tags: [security, determinism, v2, phase11]
csv_ids: ["11.3"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2274696d657374616d70227d"
    comment: "request Date.now() or /dev/random read inside VM"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 11.3 — Run a dApp that calls non-deterministic operations (Date.now()
or /dev/random) inside the VM and verify the Cartesi Machine handles them
deterministically (returning fixed values or zero).

## Steps
1. Submit an input requesting a timestamp or random value from inside the VM.
2. Assert the input is processed without crashing.
3. Verify the same input processed twice gives the same output (determinism).

## Expected Behaviour
- Date.now() inside the VM returns a deterministic value (not wall clock).
- /dev/random inside the VM is seeded deterministically.
- Two identical inputs produce identical outputs.
