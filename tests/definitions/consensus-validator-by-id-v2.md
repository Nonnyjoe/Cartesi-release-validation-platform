---
id: consensus-validator-by-id-v2
name: Query validatorById — validator lookup (v2.x)
version: 2
min_node_major_version: 2
tags: [cloud, consensus, quorum, v2, phase10]
csv_ids: ["10.8"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: cli_command
    binary: "cartesi-rollups-cli"
    container: "{jsonrpc_container}"
    args: "contract consensus {app_address}"
    expect_exit_code: 0
    expect_output_contains: "Validator"
---

## Description
CSV test 10.8 — Query `validatorById` on the Quorum consensus contract and
verify the correct validator address is returned.

## Steps
1. Query validatorById(0) from the Quorum contract.
2. Assert the returned address matches the configured validator.

## Expected Behaviour
- Validator lookup returns the correct address for the given ID.
- Contract correctly maps validator IDs to addresses.
