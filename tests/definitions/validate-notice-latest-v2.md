---
id: validate-notice-latest-v2
name: Validate notice with block=latest (fast finalization mode) (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, notice, proof, v2, phase7]
csv_ids: ["7.2"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_BLOCKCHAIN_FINALITY_OFFSET: "0"
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: notice_check
    min_count: 1
    poll_timeout: 90
  - type: cli_command
    binary: "cartesi-rollups-cli"
    container: "{jsonrpc_container}"
    args: "validate {app_address} 0"
    expect_exit_code: 0
    expect_output_contains: "validated"
---

## Description
CSV test 7.2 — Validate a notice using `--block latest` mode (fast finalization,
no confirmation blocks required).

## Steps
1. Submit a ping input.
2. Wait for notice to appear in outputs.
3. Validate with `--block latest` flag.

## Expected Behaviour
- Notice validates against `latest` block state.
- Fast finalization mode skips waiting for confirmation blocks.
