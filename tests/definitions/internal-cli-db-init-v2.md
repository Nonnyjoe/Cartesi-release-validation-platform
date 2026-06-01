---
id: internal-cli-db-init-v2
name: cartesi-rollups-cli db subcommand is available (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, db, v2, phase12]
csv_ids: ["12.1"]
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
    args: "db --help"
    expect_exit_code: 0
    expect_output_contains: "init"
---

## Description
CSV test 12.1 — Verify `cartesi-rollups-cli db` subcommand is available and
lists the `init` command in help output.

## Steps
1. Run `cartesi-rollups-cli db --help` in the jsonrpc container.
2. Assert exit code 0.
3. Assert output contains "init".

## Expected Behaviour
- The db subcommand is available with init listed.
