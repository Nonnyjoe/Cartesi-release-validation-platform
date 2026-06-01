---
id: execute-voucher-low-gas-v2
name: Execute voucher with insufficient L1 gas — tx fails gracefully (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, voucher, error-handling, v2, phase7]
csv_ids: ["7.6"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: cli_command
    binary: "cartesi-rollups-cli"
    container: "{jsonrpc_container}"
    args: "execute --help"
    expect_exit_code: 0
    expect_output_contains: "voucher"
---

## Description
CSV test 7.6 — Attempt to execute a voucher with an artificially low gas limit
and verify the transaction fails gracefully (not a node crash).

## Steps
1. Submit an input that produces a voucher.
2. Wait for voucher to appear.
3. Attempt to execute with `--gas 1000` (far below required).
4. Assert exit code non-zero and error mentions gas.

## Expected Behaviour
- Transaction fails due to insufficient gas.
- Node does not crash; failure is handled gracefully.
