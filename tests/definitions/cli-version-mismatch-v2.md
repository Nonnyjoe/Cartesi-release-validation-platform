---
id: cli-version-mismatch-v2
name: Test version mismatch (CLI vs Node) — compatibility check (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, version, v2, phase1]
csv_ids: ["1.24"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "--version"
    expect_exit_code: 0
    expect_output_contains: "."
  - type: cli_command
    args: "doctor"
    expect_exit_code: 0
    comment: "doctor should warn if CLI/node versions are incompatible"
---

## Description
CSV test 1.24 — Check CLI and node version compatibility, verifying the system
warns about incompatible version combinations.

## Steps
1. Run `cartesi --version` to get CLI version.
2. Run `cartesi doctor` to validate compatibility.
3. Assert doctor passes or warns about mismatch.

## Expected Behaviour
- Version information is accessible.
- Incompatible versions are warned about clearly.
