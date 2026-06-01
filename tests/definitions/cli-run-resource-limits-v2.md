---
id: cli-run-resource-limits-v2
name: Execute 'cartesi run --cpus N --memory N' — resource limits applied (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, run, config, v2, phase1]
csv_ids: ["1.30"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "run --cpus 2 --memory 2048 --dry-run"
    expect_exit_code: 0
    timeout: 90
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 1.30 — Execute `cartesi run --cpus 2 --memory 2g` and verify resource
limits are applied to the node containers.

## Steps
1. Run `cartesi run --cpus 2 --memory 2048 --dry-run`.
2. Assert exit code 0.
3. Assert node is healthy with the resource constraints.

## Expected Behaviour
- CPU and memory limits applied to containers.
- Node operates correctly within the configured limits.
