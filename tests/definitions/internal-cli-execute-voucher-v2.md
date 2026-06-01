---
id: internal-cli-execute-voucher-v2
name: cartesi-rollups-cli execute subcommand is available (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, egress, v2, phase12]
csv_ids: ["12.17"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
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
CSV test 12.17 — Verify `cartesi-rollups-cli execute` subcommand is available
and lists voucher execution in help output.

## Steps
1. Run `cartesi-rollups-cli execute --help`.
2. Assert exit code 0.
3. Assert output contains "voucher".

## Expected Behaviour
- Execute subcommand is available with voucher listed.
