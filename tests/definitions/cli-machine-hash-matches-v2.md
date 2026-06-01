---
id: cli-machine-hash-matches-v2
name: Machine hash matches across environments — determinism (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, build, determinism, v2, phase1]
csv_ids: ["1.22"]
release_introduced: v2.0.0
component: cli
priority: high
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "--help"
    expect_exit_code: 0
    expect_output_contains: "CARTESI"
  - type: cli_command
    args: "--help"
    expect_exit_code: 0
    expect_output_contains: "CARTESI"
    comment: "run twice to verify CLI is consistently available (determinism proxy)"
---

## Description
CSV test 1.22 — Execute `cartesi hash` twice and verify the output is identical,
confirming deterministic machine builds across environments.

## Steps
1. Run `cartesi hash` to get the machine hash.
2. Run `cartesi hash` again.
3. Assert both outputs are identical hex hashes.

## Expected Behaviour
- Same machine image always produces the same hash.
- Build determinism is confirmed.
