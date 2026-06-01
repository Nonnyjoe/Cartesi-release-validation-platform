---
id: cli-status-stopped-v2
name: Execute 'cartesi status' on stopped node — reports 'stopped' (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, status, v2, phase1]
csv_ids: ["1.12"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 30
requires: []
assertions:
  - type: cli_command
    args: "status"
    expect_exit_code: 0
---

## Description
CSV test 1.12 — Execute `cartesi status` when no node is running and verify
it reports 'stopped' status.

## Setup
No node should be running when this test executes.

## Steps
1. Run `cartesi status` with no active node.
2. Assert exit code 0.
3. Assert output contains "stopped".

## Expected Behaviour
- Status command correctly identifies node is not running.
- Clear "stopped" status is reported.
