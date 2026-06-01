---
id: internal-cli-deploy-authority-v2
name: cartesi-rollups-cli deploy subcommand is available (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, deployment, v2, phase12]
csv_ids: ["12.11"]
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
    args: "deploy --help"
    expect_exit_code: 0
    expect_output_contains: "authority"
---

## Description
CSV test 12.11 — Verify `cartesi-rollups-cli deploy` subcommand is available
and lists the `authority` subcommand.

## Steps
1. Run `cartesi-rollups-cli deploy --help`.
2. Assert exit code 0.
3. Assert output contains "authority".

## Expected Behaviour
- Deploy subcommand is available with authority listed.
