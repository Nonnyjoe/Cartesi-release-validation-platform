---
id: internal-cli-read-inputs-v2
name: cartesi-rollups-cli read inputs lists processed inputs (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, read, v2, phase12]
csv_ids: ["12.19"]
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
    args: "read inputs {app_address} --limit 5"
    expect_exit_code: 0
---

## Description
CSV test 12.19 — Read inputs for the deployed application using
`cartesi-rollups-cli read inputs` with a pagination limit.

## Steps
1. Run `cartesi-rollups-cli read inputs {app_address} --limit 5`.
2. Assert exit code 0.

## Expected Behaviour
- Input records listed from DB with pagination support.
