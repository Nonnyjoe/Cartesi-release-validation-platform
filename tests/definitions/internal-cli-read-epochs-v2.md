---
id: internal-cli-read-epochs-v2
name: cartesi-rollups-cli read epochs lists epoch records (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, read, v2, phase12]
csv_ids: ["12.18"]
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
    args: "read epochs {app_address}"
    expect_exit_code: 0
---

## Description
CSV test 12.18 — Run `cartesi-rollups-cli read epochs {app_address}` and verify
epoch records are listed.

## Steps
1. Run `cartesi-rollups-cli read epochs {app_address}`.
2. Assert exit code 0.

## Expected Behaviour
- Epoch records are listed from the database.
