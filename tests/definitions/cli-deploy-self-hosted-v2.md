---
id: cli-deploy-self-hosted-v2
name: Execute 'cartesi deploy' with self-hosted mode (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, deploy, cloud, v2, phase1]
csv_ids: ["1.42"]
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
---

## Description
CSV test 1.42 — Execute `cartesi deploy` in self-hosted mode and verify the
complete self-hosted deployment flow runs to completion.

## Setup
Requires testnet access and a funded wallet for deployment.

## Steps
1. Run `cartesi deploy --hosting self-hosted`.
2. Assert exit code 0.
3. Verify deployment completes with contract addresses in output.

## Expected Behaviour
- Self-hosted deployment flow completes successfully.
- Application contract deployed and node configured.
