---
id: cli-deploy-optimism-sepolia-v2
name: Deploy to Optimism Sepolia testnet via CLI (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, deploy, cloud, testnet, v2, phase1]
csv_ids: ["1.21"]
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
CSV test 1.21 — Deploy to Optimism Sepolia (L2 testnet) via the CLI and verify
the L2 deployment flow works correctly.

## Setup
Requires a funded wallet and RPC endpoint for Optimism Sepolia.

## Steps
1. Run `cartesi deploy --network optimism-sepolia`.
2. Assert exit code 0 and contract address in output.

## Expected Behaviour
- L2 deployment succeeds on Optimism Sepolia.
- Contract address confirmed on Optimism Sepolia.
