---
id: security-deadline-limit-v2
name: Per-app deadline limit via execution-parameters — VM halts (v2.x)
version: 2
min_node_major_version: 2
tags: [security, limits, deadline, v2, phase11]
csv_ids: ["11.10"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: cli_command
    binary: "cartesi-rollups-cli"
    container: "{jsonrpc_container}"
    args: "app execution-parameters list {app_address}"
    expect_exit_code: 0
    expect_output_contains: "advance_max_deadline" 
---

## Description
CSV test 11.10 — Set a tight per-app advance deadline via execution parameters
and verify the VM halts when the deadline is exceeded.

## Steps
1. Set advance deadline to 100ms via execution-parameters.
2. Submit an input that requires more than 100ms to process.
3. Assert the advancer logs mention deadline exceeded.

## Expected Behaviour
- VM halts when configured deadline is exceeded.
- Deadline is enforced per-app, not globally.
- Input is marked as rejected/halted (not stuck).
