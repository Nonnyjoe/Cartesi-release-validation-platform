---
id: internal-cli-db-check-mismatch-v2
name: cartesi-rollups-cli db check-version on running node reports version (v2.x)
version: 2
min_node_major_version: 2
tags: [internal-cli, db, standalone, v2, phase12]
csv_ids: ["12.3"]
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
CSV test 12.3 — Run `cartesi-rollups-cli db check-version` against the live node DB
and verify it reports the schema version (proxy for schema health check).

## Steps
1. Run `cartesi-rollups-cli db check-version` in the jsonrpc container.
2. Assert exit code 0.
3. Assert output contains "version".

## Expected Behaviour
- DB version check succeeds on the live node schema.
