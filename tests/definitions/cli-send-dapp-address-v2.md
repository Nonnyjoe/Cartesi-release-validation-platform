---
id: cli-send-dapp-address-v2
name: Execute 'cartesi send dapp-address' — address relay sent (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, send, v2, phase1]
csv_ids: ["1.41"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "send --help"
    expect_exit_code: 0
    expect_output_contains: "application"
---

## Description
CSV test 1.41 — Execute `cartesi send dapp-address` and verify the dApp address
relay is sent to the application via the InputBox.

## Steps
1. Run `cartesi send dapp-address`.
2. Assert exit code 0.
3. Assert the relay input appears in cartesi_listInputs.

## Expected Behaviour
- DApp address relay input is submitted to the InputBox.
- Input indexed by the node.
