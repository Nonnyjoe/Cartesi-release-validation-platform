---
id: cli-cast-interop-v2
name: Execute standard Ethereum cast commands — tooling interoperability (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, tooling, interop, v2, phase1]
csv_ids: ["1.25"]
release_introduced: v2.0.0
component: cli
priority: low
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "send --help"
    expect_exit_code: 0
    expect_output_contains: "application"
    comment: "verify cartesi send subcommand is available (cast tooling interop)"
---

## Description
CSV test 1.25 — Verify that the Cartesi CLI works alongside standard Ethereum
tooling (cast, forge) without conflicts or incompatibilities.

## Steps
1. Run `cartesi send ether` to confirm Cartesi CLI is compatible.
2. Assert no conflicts with standard Ethereum tooling in the environment.

## Expected Behaviour
- Cartesi CLI coexists with standard Ethereum tooling.
- No version conflicts or path issues.
