---
id: cli-send-erc721-v2
name: Execute 'cartesi send erc721' with valid args (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, send, erc721, v2, phase1]
csv_ids: ["1.39"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 90
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
CSV test 1.39 — Execute `cartesi send erc721` with valid arguments and verify
the ERC721 send subcommand routes correctly.

## Steps
1. Run `cartesi send erc721 --token-id 1 --token 0x...`.
2. Assert exit code 0.

## Expected Behaviour
- ERC721 send subcommand works correctly.
- NFT deposit routed to the ERC721Portal.
