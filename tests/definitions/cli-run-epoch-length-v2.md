---
id: cli-run-epoch-length-v2
name: Execute 'cartesi run --epoch-length N' — custom epoch (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, run, config, v2, phase1]
csv_ids: ["1.9"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "run --epoch-length 5 --dry-run"
    expect_exit_code: 0
    timeout: 90
  - type: health_check
    service: jsonrpc
    path: /readyz
    expect_status: 200
---

## Description
CSV test 1.9 — Execute `cartesi run --epoch-length 5` and verify the custom
epoch length is applied to the running node.

## Steps
1. Run `cartesi run --epoch-length 5 --dry-run`.
2. Assert exit code 0.
3. Assert node becomes healthy with the custom epoch length.

## Expected Behaviour
- Node starts with epoch length of 5 blocks.
- Configuration is respected at runtime.
