---
id: internal-cli-app-list-pagination-v2
name: cartesi-rollups-cli app list returns registered applications (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, app-mgmt, v2, phase12]
csv_ids: ["12.5"]
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
CSV test 12.5 — Run `cartesi-rollups-cli app list` and verify at least one
application is listed with ENABLED status.

## Steps
1. Run `cartesi-rollups-cli app list` in the jsonrpc container.
2. Assert exit code 0.
3. Assert output contains "ENABLED".

## Expected Behaviour
- At least one app is listed with ENABLED status.
