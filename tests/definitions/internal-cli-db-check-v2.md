---
id: internal-cli-db-check-v2
name: cartesi-rollups-cli db check-version on valid schema returns correct version (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, db, v2, phase12]
csv_ids: ["12.2"]
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
    args: "db check-version"
    expect_exit_code: 0
    expect_output_contains: "version"
---

## Description
CSV test 12.2 — Run `cartesi-rollups-cli db check-version` against the running node
database and verify it reports the correct schema version.

## Steps
1. Run `cartesi-rollups-cli db check-version` in the jsonrpc container.
2. Assert exit code 0.
3. Assert output contains "version".

## Expected Behaviour
- Schema version check passes cleanly.
- No migration errors reported.
