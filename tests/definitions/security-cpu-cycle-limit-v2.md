---
id: security-cpu-cycle-limit-v2
name: Per-app CPU cycle limit via execution-parameters halts VM at threshold (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, security, limits, vm, cpu, v2, phase11]
csv_ids: ["11.9"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a22696e66696e6974655f6c6f6f70227d"
    comment: '{"action":"infinite_loop"} — triggers CPU cycle limit'
  - type: log_contains
    component: advancer
    pattern: "cycle"
    timeout_seconds: 60
---

## Description
CSV test 11.9 — Set a per-app CPU cycle limit via execution-parameters and
verify the VM halts at the configured cycle threshold.

## Setup
Configure `CARTESI_MACHINE_MAX_CYCLES=10000000` or equivalent in execution params.

## Steps
1. Submit an infinite loop payload.
2. Assert the advancer logs a cycle limit exceeded error.

## Expected Behaviour
- VM halts at the configured cycle threshold.
- Error is logged (not a silent hang).
