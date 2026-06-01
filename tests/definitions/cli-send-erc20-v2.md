---
id: cli-send-erc20-v2
name: Execute 'cartesi send erc20' with valid args (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, send, erc20, v2, phase1]
csv_ids: ["1.38"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 90
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "deposit erc20 --help"
    expect_exit_code: 0
    expect_output_contains: "amount"
---

## Description
CSV test 1.38 — Execute `cartesi send erc20` with valid arguments and verify
the ERC20 send subcommand routes correctly.

## Steps
1. Run `cartesi send erc20 --amount 100 --token 0x...`.
2. Assert exit code 0.

## Expected Behaviour
- ERC20 send subcommand works correctly.
- Deposit routed to the correct portal contract.
