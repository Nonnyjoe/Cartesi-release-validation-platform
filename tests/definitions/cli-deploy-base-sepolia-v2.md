---
id: cli-deploy-base-sepolia-v2
name: Deploy to Base Sepolia testnet via CLI (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, deploy, cloud, testnet, v2, phase1]
csv_ids: ["1.19"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 300
requires: []
assertions:
  - type: cli_command
    args: "deploy --help"
    expect_exit_code: 0
    timeout: 240
    expect_output_contains: "DEPRECATED"
---

## Description
CSV test 1.19 — Deploy to the Base Sepolia public testnet and verify the
deployment flow completes with a contract address.

## Setup
Requires a funded wallet and RPC endpoint for Base Sepolia.

## Steps
1. Run `cartesi deploy --network base-sepolia`.
2. Assert exit code 0 and contract address in output.

## Expected Behaviour
- Deployment succeeds on Base Sepolia.
- Contract address confirmed on-chain.
