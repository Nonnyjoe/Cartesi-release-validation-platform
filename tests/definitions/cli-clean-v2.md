---
id: cli-clean-v2
name: Execute 'cartesi clean' after build — removes artifacts (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, clean, v2, phase1]
csv_ids: ["1.6"]
release_introduced: v2.0.0
component: cli
priority: low
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "clean"
    expect_exit_code: 0
---

## Description
CSV test 1.6 — Execute `cartesi clean` after a build and verify build artifacts
are removed from the project directory.

## Steps
1. Run `cartesi clean`.
2. Assert exit code 0.
3. Verify build artifacts are removed.

## Expected Behaviour
- Build artifacts cleaned up successfully.
- Project directory is in a clean state.
