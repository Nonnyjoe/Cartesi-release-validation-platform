---
id: internal-cli-send-hex-v2
name: cartesi-rollups-cli send subcommand is available (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, inputs, v2, phase12]
csv_ids: ["12.12"]
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
    args: "send --help"
    expect_exit_code: 0
    expect_output_contains: "hex"
---

## Description
CSV test 12.12 — Verify `cartesi-rollups-cli send` subcommand is available
and supports the --hex flag.

## Steps
1. Run `cartesi-rollups-cli send --help`.
2. Assert exit code 0.
3. Assert output contains "hex".

## Expected Behaviour
- Send subcommand is available with --hex flag documented.
