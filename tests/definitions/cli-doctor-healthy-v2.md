---
id: cli-doctor-healthy-v2
name: Execute 'cartesi doctor' on healthy system (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, doctor, v2, phase1]
csv_ids: ["1.1"]
release_introduced: v2.0.0
component: cli
priority: high
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "doctor --help"
    expect_exit_code: 0
    expect_output_contains: "doctor"
---

## Description
CSV test 1.1 — Execute `cartesi doctor` on a healthy system where all
dependencies are present and verify all checks pass.

## Steps
1. Run `cartesi doctor` inside the CLI sandbox container.
2. Assert exit code 0.
3. Assert output contains confirmation of passing checks.

## Expected Behaviour
- All dependency checks pass (Docker, Node.js, etc.).
- Exit code 0.
- No error messages.
