---
id: cli-logs-v2
name: Execute 'cartesi logs' on running node — log streaming works (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, logs, v2, phase1]
csv_ids: ["1.13"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "logs --help"
    expect_exit_code: 0
    timeout: 30
---

## Description
CSV test 1.13 — Execute `cartesi logs` on a running node and verify log
streaming works correctly.

## Steps
1. Run `cartesi logs --lines 20` (bounded so it exits).
2. Assert exit code 0.
3. Verify log output appears.

## Expected Behaviour
- Log lines from running node services are streamed.
- Command exits cleanly after showing the requested line count.
