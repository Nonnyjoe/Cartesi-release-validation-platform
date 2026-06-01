---
id: cli-help-v2
name: Execute 'cartesi help' and 'cartesi <cmd> --help' — docs accessible (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, help, v2, phase1]
csv_ids: ["1.14"]
release_introduced: v2.0.0
component: cli
priority: low
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "--help"
    expect_exit_code: 0
    expect_output_contains: "cartesi"
  - type: cli_command
    args: "send --help"
    expect_exit_code: 0
    expect_output_contains: "send"
---

## Description
CSV test 1.14 — Execute `cartesi --help` and `cartesi send --help` and verify
documentation is accessible and accurate.

## Steps
1. Run `cartesi --help`.
2. Assert exit code 0 and output contains "cartesi".
3. Run `cartesi send --help`.
4. Assert exit code 0 and output mentions send.

## Expected Behaviour
- Top-level help is accessible.
- Subcommand help is accurate and informative.
