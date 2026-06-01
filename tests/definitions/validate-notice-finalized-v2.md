---
id: validate-notice-finalized-v2
name: Validate notice with block=finalized (production mode) (v2.x)
version: 1
min_node_major_version: 2
tags: [egress, notice, proof, v2, phase7]
csv_ids: ["7.3"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 240
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: notice_check
    min_count: 1
    poll_timeout: 120
  - type: cli_command
    binary: "cartesi-rollups-cli"
    container: "{jsonrpc_container}"
    args: "validate {app_address} 0"
    expect_exit_code: 0
    expect_output_contains: "validated"
---

## Description
CSV test 7.3 — Validate a notice using `--block finalized` mode (production
finality setting, waiting for finalized block state).

## Steps
1. Submit a ping input.
2. Wait for notice and epoch claim.
3. Validate with `--block finalized` flag.

## Expected Behaviour
- Notice validates against the finalized block state.
- Production finality mode ensures claim is settled before validation.
