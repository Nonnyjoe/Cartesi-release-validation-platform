---
id: cli-address-book-v2
name: Execute 'cartesi address-book' prints valid contract addresses (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, address-book, v2, phase1]
csv_ids: ["1.15"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 30
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "address-book"
    expect_exit_code: 0
    expect_output_contains: "0x"
---

## Description
CSV test 1.15 — Execute `cartesi address-book` and verify it prints valid
Ethereum contract addresses.

## Steps
1. Run `cartesi address-book` inside the CLI container.
2. Assert exit code 0.
3. Assert output contains hex addresses (0x...).

## Expected Behaviour
- Prints portal addresses, InputBox, and other contract addresses.
- All addresses are valid 0x-prefixed hex strings.
