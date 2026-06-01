---
id: internal-cli-app-exec-params-set-v2
name: cartesi-rollups-cli app execution-parameters list shows configured limits (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, app-mgmt, v2, phase12]
csv_ids: ["12.9"]
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
CSV test 12.9 — Verify `cartesi-rollups-cli app execution-parameters list` shows
the configured execution limits for the application.

## Steps
1. Run `cartesi-rollups-cli app execution-parameters list {app_address}`.
2. Assert exit code 0.
3. Assert output contains "advance_max_cycles".

## Expected Behaviour
- Execution parameters are accessible and contain cycle limits.
