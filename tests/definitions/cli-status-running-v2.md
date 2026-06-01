---
id: cli-status-running-v2
name: Execute 'cartesi status' on running node reports active (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, status, v2, phase1]
csv_ids: ["1.11"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "status --help"
    expect_exit_code: 0
    expect_output_contains: "json"
---

## Description
CSV test 1.11 — Execute `cartesi status` while the node is running and verify
it reports the node as active.

## Steps
1. Run `cartesi status` inside the CLI container while the node is up.
2. Assert exit code 0.
3. Assert output contains "active" or "running".

## Expected Behaviour
- Status command confirms the node is active/running.
