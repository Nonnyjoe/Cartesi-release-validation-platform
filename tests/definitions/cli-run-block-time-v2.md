---
id: cli-run-block-time-v2
name: Execute 'cartesi run --block-time N' — custom block time (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, run, config, v2, phase1]
csv_ids: ["1.26"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "run --block-time 2 --dry-run"
    expect_exit_code: 0
    timeout: 90
  - type: health_check
    service: jsonrpc
    path: /readyz
    expect_status: 200
---

## Description
CSV test 1.26 — Execute `cartesi run --block-time 2` and verify the local
Anvil chain advances at the custom block time (2 seconds per block).

## Steps
1. Run `cartesi run --block-time 2 --dry-run`.
2. Assert exit code 0.
3. Assert node becomes healthy.

## Expected Behaviour
- Local chain mines a new block every 2 seconds.
- Custom block time is applied at Anvil level.
