---
id: cli-run-verbose-v2
name: Execute 'cartesi run --verbose' — verbose service logs shown (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, run, v2, phase1]
csv_ids: ["1.28"]
release_introduced: v2.0.0
component: cli
priority: low
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "run -v --dry-run"
    expect_exit_code: 0
    timeout: 90
---

## Description
CSV test 1.28 — Execute `cartesi run --verbose` and verify verbose service
log output is shown.

## Steps
1. Run `cartesi run -v --dry-run`.
2. Assert exit code 0.

## Expected Behaviour
- Node starts with verbose logging enabled.
- More detailed output appears in service logs.
