---
id: security-jsonrpc-flag-v2
name: Test --jsonrpc flag on node-cli read commands (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, tooling, v2, phase11]
csv_ids: ["11.6"]
release_introduced: v2.0.0
component: cli
priority: low
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    binary: "cartesi-rollups-cli"
    container: "{jsonrpc_container}"
    args: "read inputs {app_address}"
    expect_exit_code: 0
---

## Description
CSV test 11.6 — Test the `--jsonrpc` flag on `cartesi-rollups-cli read`
commands to verify the new flag is accepted and produces JSON output.

## Steps
1. Run `cartesi-rollups-cli read inputs --jsonrpc`.
2. Assert exit code 0.
3. Verify output is valid JSON format.

## Expected Behaviour
- --jsonrpc flag is accepted without error.
- Output format switches to JSON.
