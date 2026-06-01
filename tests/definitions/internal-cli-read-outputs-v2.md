---
id: internal-cli-read-outputs-v2
name: cartesi-rollups-cli read outputs lists outputs (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, read, v2, phase12]
csv_ids: ["12.20"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 90
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    binary: "cartesi-rollups-cli"
    container: "{jsonrpc_container}"
    args: "read outputs {app_address}"
    expect_exit_code: 0
---

## Description
CSV test 12.20 — Read outputs for the deployed application using
`cartesi-rollups-cli read outputs`.

## Steps
1. Run `cartesi-rollups-cli read outputs {app_address}`.
2. Assert exit code 0.

## Expected Behaviour
- Output records listed from DB.
