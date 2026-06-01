---
id: internal-cli-app-exec-params-get-v2
name: cartesi-rollups-cli app execution-parameters list returns defaults (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, app-mgmt, v2, phase12]
csv_ids: ["12.8"]
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
    args: "app execution-parameters list {app_address}"
    expect_exit_code: 0
    expect_output_contains: "advance_max_cycles"
---

## Description
CSV test 12.8 — Run `cartesi-rollups-cli app execution-parameters list` and
verify it returns the default execution parameters for the app.

## Steps
1. Run `cartesi-rollups-cli app execution-parameters list {app_address}`.
2. Assert exit code 0.
3. Assert output contains "advance_max_cycles".

## Expected Behaviour
- Default execution parameters are returned.
