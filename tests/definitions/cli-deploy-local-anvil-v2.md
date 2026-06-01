---
id: cli-deploy-local-anvil-v2
name: Deploy to local Anvil via CLI (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, deploy, anvil, v2, phase1]
csv_ids: ["1.18"]
release_introduced: v2.0.0
component: cli
priority: high
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "deploy --help"
    expect_exit_code: 0
    expect_output_contains: "DEPRECATED"
---

## Description
CSV test 1.18 — Deploy an application to the local Anvil chain via the
`cartesi deploy` CLI command and verify integration with the local blockchain.

## Steps
1. Run `cartesi deploy --hosting self-hosted` targeting local Anvil.
2. Assert exit code 0.
3. Assert deployment output includes a contract address.

## Expected Behaviour
- Application deployed to local Anvil successfully.
- CartesiDApp contract address printed in output.
