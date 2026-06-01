---
id: cli-deposit-missing-args-v2
name: Execute 'cartesi deposit' with missing arguments — CLI catches error (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, deposit, error-handling, v2, phase1]
csv_ids: ["1.17"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "deposit --help"
    expect_exit_code: 0
    expect_output_contains: "application"
---

## Description
CSV test 1.17 — Execute `cartesi deposit` without required arguments and verify
the CLI catches the missing parameters and shows a helpful error.

## Steps
1. Run `cartesi deposit` with no arguments.
2. Assert non-zero exit code.
3. Assert output mentions missing required parameters.

## Expected Behaviour
- CLI validates required arguments before execution.
- Clear error message listing required parameters.
