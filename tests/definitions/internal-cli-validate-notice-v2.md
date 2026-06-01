---
id: internal-cli-validate-notice-v2
name: cartesi-rollups-cli validate subcommand is available (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, egress, v2, phase12]
csv_ids: ["12.16"]
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
    args: "validate --help"
    expect_exit_code: 0
    expect_output_contains: "notice"
---

## Description
CSV test 12.16 — Verify `cartesi-rollups-cli validate` subcommand is available
and supports notice validation.

## Steps
1. Run `cartesi-rollups-cli validate --help`.
2. Assert exit code 0.
3. Assert output contains "notice".

## Expected Behaviour
- Validate subcommand is available with notice listed.
