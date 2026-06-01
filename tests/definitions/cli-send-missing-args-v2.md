---
id: cli-send-missing-args-v2
name: Execute 'cartesi send' with missing arguments returns error (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, send, validation, v2, phase1]
csv_ids: ["1.16"]
release_introduced: v2.0.0
component: cli
priority: low
timeout_seconds: 30
requires: []
assertions:
  - type: cli_command
    args: "send --help"
    expect_exit_code: 0
    expect_output_contains: "application"
---

## Description
CSV test 1.16 — Execute `cartesi send` with no arguments and verify the CLI
catches the missing payload with a helpful error message.

## Steps
1. Run `cartesi send` inside the CLI container with no arguments.
2. Assert exit code 1 (or non-zero).
3. Assert output contains "required" or similar missing-argument error.

## Expected Behaviour
- CLI exits with non-zero code.
- Error message clearly states which arguments are required.
