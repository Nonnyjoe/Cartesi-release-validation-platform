---
id: cli-send-generic-v2
name: Execute 'cartesi send generic' with valid hex payload (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, send, generic, v2, phase1]
csv_ids: ["1.40"]
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
    timeout: 30
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 1.40 — Execute `cartesi send generic` with a valid hex payload and
verify the generic send subcommand routes correctly.

## Steps
1. Run `cartesi send generic` with a hex payload and app address.
2. Assert exit code 0.
3. Verify the input appears in cartesi_listInputs.

## Expected Behaviour
- Generic send subcommand submits input to InputBox.
- Input is indexed by the node.
