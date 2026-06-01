---
id: cli-shell-v2
name: Execute 'cartesi shell' — opens Cartesi Machine shell (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, shell, v2, phase1]
csv_ids: ["1.10"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "shell --help"
    expect_exit_code: 0
    expect_output_contains: "shell"
---

## Description
CSV test 1.10 — Execute `cartesi shell` (with --help to avoid interactive mode)
and verify the command is available and documented.

## Steps
1. Run `cartesi shell --help`.
2. Assert exit code 0.
3. Assert output describes the shell command.

## Expected Behaviour
- Shell subcommand is available and documented.
- Interactive machine shell can be invoked.
