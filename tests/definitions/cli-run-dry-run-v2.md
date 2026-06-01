---
id: cli-run-dry-run-v2
name: Execute 'cartesi run --dry-run' — prints config without starting (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, run, v2, phase1]
csv_ids: ["1.29"]
release_introduced: v2.0.0
component: cli
priority: low
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "run --help"
    expect_exit_code: 0
    expect_output_contains: "dry-run"
---

## Description
CSV test 1.29 — Execute `cartesi run --dry-run` and verify the Docker Compose
configuration is printed without actually starting any services.

## Steps
1. Run `cartesi run --dry-run`.
2. Assert exit code 0.
3. Assert output contains compose service definitions.

## Expected Behaviour
- No containers are started.
- Compose config is printed to stdout for review.
