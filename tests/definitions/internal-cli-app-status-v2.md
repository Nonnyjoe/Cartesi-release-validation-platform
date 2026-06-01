---
id: internal-cli-app-status-v2
name: cartesi-rollups-cli app list shows ENABLED status for registered app (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, app-mgmt, v2, phase12]
csv_ids: ["12.6"]
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
    args: "app list"
    expect_exit_code: 0
    expect_output_contains: "ENABLED"
---

## Description
CSV test 12.6 — Run `cartesi-rollups-cli app list` and verify the deployed
application has ENABLED status.

## Steps
1. Run `cartesi-rollups-cli app list`.
2. Assert exit code 0.
3. Assert output contains "ENABLED".

## Expected Behaviour
- Application shows ENABLED status in app list.
