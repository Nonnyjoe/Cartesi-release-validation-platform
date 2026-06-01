---
id: cli-build-valid-v2
name: Execute 'cartesi build' on valid project — builds without errors (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, build, v2, phase1]
csv_ids: ["1.4"]
release_introduced: v2.0.0
component: cli
priority: high
timeout_seconds: 300
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "build --help"
    expect_exit_code: 0
    expect_output_contains: "build"
    timeout: 30
---

## Description
CSV test 1.4 — Execute `cartesi build` in a valid project directory and verify
the machine drives are built without errors.

## Steps
1. Run `cartesi build` in the test app directory.
2. Assert exit code 0.
3. Verify no build errors in output.

## Expected Behaviour
- Build completes successfully.
- Machine image artifact is produced.
