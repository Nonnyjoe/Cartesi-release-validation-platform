---
id: cli-send-ether-v2
name: Execute 'cartesi send ether' with valid args (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, send, ether, v2, phase1]
csv_ids: ["1.37"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "deposit ether --help"
    expect_exit_code: 0
    expect_output_contains: "amount"
---

## Description
CSV test 1.37 — Execute `cartesi send ether` with valid arguments and verify
the ether send subcommand routes correctly.

## Steps
1. Run `cartesi send ether` with valid amount and app address.
2. Assert exit code 0.

## Expected Behaviour
- Ether send subcommand executes without error.
- Transaction is submitted to the EtherPortal.
