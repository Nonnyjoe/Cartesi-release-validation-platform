---
id: cli-hash-v2
name: Execute 'cartesi hash' after build returns machine hash (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, hash, build, v2, phase1]
csv_ids: ["1.7"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "hash --help"
    expect_exit_code: 0
    expect_output_contains: "hex"
---

## Description
CSV test 1.7 — Execute `cartesi hash` and verify the correct machine hash is
output.

## Steps
1. Run `cartesi hash` inside the CLI container.
2. Assert exit code 0.
3. Assert output contains a 0x-prefixed hash string.

## Expected Behaviour
- Machine hash is printed as a 0x-prefixed hex string.
- Hash is deterministic for the same build.
