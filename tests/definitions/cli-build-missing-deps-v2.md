---
id: cli-build-missing-deps-v2
name: Execute 'cartesi build' with missing dependencies — graceful error (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, build, error-handling, v2, phase1]
csv_ids: ["1.5"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "build"
    expect_exit_code: 1
    expect_output_contains: "FAILED"
---

## Description
CSV test 1.5 — Execute `cartesi build` in a directory with missing build
dependencies and verify the CLI produces a helpful error message.

## Setup
Run this test in a directory that is missing required build configuration.

## Steps
1. Run `cartesi build` in an incomplete project.
2. Assert non-zero exit code.
3. Assert output contains a helpful error message.

## Expected Behaviour
- Build fails gracefully with a clear error message.
- Error message directs user to what's missing.
