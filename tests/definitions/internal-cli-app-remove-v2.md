---
id: internal-cli-app-remove-v2
name: cartesi-rollups-cli app management commands available (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, app-mgmt, v2, phase12]
csv_ids: ["12.7"]
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
    args: "app --help"
    expect_exit_code: 0
    expect_output_contains: "register"
---

## Description
CSV test 12.7 — Verify `cartesi-rollups-cli app` subcommand lists the register
and remove subcommands in help output.

## Steps
1. Run `cartesi-rollups-cli app --help`.
2. Assert exit code 0.
3. Assert output contains "register".

## Expected Behaviour
- App management subcommands (register, remove) are listed.
