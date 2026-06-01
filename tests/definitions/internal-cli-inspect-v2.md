---
id: internal-cli-inspect-v2
name: cartesi-rollups-cli inspect subcommand is available (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, inspect, v2, phase12]
csv_ids: ["12.15"]
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
    args: "inspect --help"
    expect_exit_code: 0
    expect_output_contains: "payload"
---

## Description
CSV test 12.15 — Verify `cartesi-rollups-cli inspect` subcommand is available
and accepts payload arguments.

## Steps
1. Run `cartesi-rollups-cli inspect --help`.
2. Assert exit code 0.
3. Assert output contains "payload".

## Expected Behaviour
- Inspect subcommand is available with payload argument documented.
