---
id: internal-cli-contract-summary-v2
name: cartesi-rollups-cli contract subcommand is available (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, diagnostics, v2, phase12]
csv_ids: ["12.22"]
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
    args: "contract --help"
    expect_exit_code: 0
    expect_output_contains: "app"
---

## Description
CSV test 12.22 — Verify `cartesi-rollups-cli contract` subcommand is available
and lists app-related commands.

## Steps
1. Run `cartesi-rollups-cli contract --help`.
2. Assert exit code 0.
3. Assert output contains "app".

## Expected Behaviour
- Contract subcommand is available.
