---
id: internal-cli-app-register-v2
name: cartesi-rollups-cli app list returns apps with ENABLED state (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, app-mgmt, v2, phase12]
csv_ids: ["12.4"]
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
CSV test 12.4 — Verify `cartesi-rollups-cli app list` returns registered apps
with ENABLED state.

## Steps
1. Run `cartesi-rollups-cli app list`.
2. Assert exit code 0.
3. Assert output contains "ENABLED".

## Expected Behaviour
- Apps are listed with ENABLED status.
