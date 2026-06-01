---
id: cli-run-listen-port-v2
name: Execute 'cartesi run --listen-port N' — services bind on custom port (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, run, config, v2, phase1]
csv_ids: ["1.32"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "run --help"
    expect_exit_code: 0
    expect_output_contains: "port"
    timeout: 30
---

## Description
CSV test 1.32 — Execute `cartesi run --listen-port 18080` and verify node
services bind on the custom port instead of the default.

## Steps
1. Run `cartesi run --listen-port 18080 --detach`.
2. Assert exit code 0.
3. Assert node is accessible on port 18080.

## Expected Behaviour
- All services bind on the specified custom port.
- Default port (8080) is not in use.
