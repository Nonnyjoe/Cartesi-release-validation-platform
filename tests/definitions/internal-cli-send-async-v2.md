---
id: internal-cli-send-async-v2
name: cartesi-rollups-cli send --async flag is available (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, inputs, v2, phase12]
csv_ids: ["12.13"]
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
    expect_output_contains: "async"
---

## Description
CSV test 12.13 — Verify `cartesi-rollups-cli send` supports the --async flag.

## Steps
1. Run `cartesi-rollups-cli send --help`.
2. Assert exit code 0.
3. Assert output contains "async".

## Expected Behaviour
- Send subcommand documents the --async flag.
