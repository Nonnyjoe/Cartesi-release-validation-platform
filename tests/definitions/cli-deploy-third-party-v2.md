---
id: cli-deploy-third-party-v2
name: Execute 'cartesi deploy --hosting=third-party' — not supported error (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, deploy, error-handling, v2, phase1]
csv_ids: ["1.44"]
release_introduced: v2.0.0
component: cli
priority: low
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "deploy --hosting third-party"
    expect_exit_code: 1
    expect_output_contains: "error"
---

## Description
CSV test 1.44 — Execute `cartesi deploy --hosting=third-party` and verify
a clear "not supported yet" error is returned.

## Steps
1. Run `cartesi deploy --hosting third-party`.
2. Assert non-zero exit code.
3. Assert output contains "not supported".

## Expected Behaviour
- Third-party hosting is rejected with a clear error.
- Error message indicates the feature is not yet supported.
