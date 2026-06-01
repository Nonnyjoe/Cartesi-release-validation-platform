---
id: cli-run-v2
name: Execute 'cartesi run' — local node boots successfully (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, run, v2, phase1]
csv_ids: ["1.8"]
release_introduced: v2.0.0
component: cli
priority: high
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
CSV test 1.8 — Execute `cartesi run` (with --dry-run) and verify the local node
boots successfully and becomes healthy.

## Steps
1. Run `cartesi run --dry-run`.
2. Assert exit code 0 (detach returns quickly).
3. Assert JSON-RPC service is healthy.

## Expected Behaviour
- All node services start successfully.
- Node becomes healthy within the timeout.
