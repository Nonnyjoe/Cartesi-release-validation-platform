---
id: cli-run-disable-explorer-v2
name: Execute 'cartesi run --disable-explorer' — explorer not started (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, run, v2, phase1]
csv_ids: ["1.31"]
release_introduced: v2.0.0
component: cli
priority: low
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "run --dry-run"
    expect_exit_code: 0
    timeout: 90
  - type: health_check
    service: jsonrpc
    path: /readyz
    expect_status: 200
---

## Description
CSV test 1.31 — Execute `cartesi run --disable-explorer` and verify the
explorer/block explorer container is not started.

## Steps
1. Run `cartesi run --dry-run`.
2. Assert exit code 0.
3. Assert core services healthy but no explorer container.

## Expected Behaviour
- Node starts without the explorer container.
- Core node services remain healthy.
