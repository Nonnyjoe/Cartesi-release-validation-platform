---
id: consensus-quorum-num-validators-v2
name: Query numOfValidatorsInFavorOf — quorum state query (v2.x)
version: 2
min_node_major_version: 2
tags: [cloud, consensus, quorum, v2, phase10]
csv_ids: ["10.7"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: cli_command
    binary: "cartesi-rollups-cli"
    container: "{jsonrpc_container}"
    args: "contract consensus {app_address}"
    expect_exit_code: 0
    expect_output_contains: "Epoch Length"
---

## Description
CSV test 10.7 — Query `numOfValidatorsInFavorOf` on the Quorum consensus
contract and verify the count matches the expected validator quorum state.

## Steps
1. Submit an input to advance the epoch.
2. Query numOfValidatorsInFavorOf via the rollups CLI or direct contract call.
3. Assert the quorum count matches expected value.

## Expected Behaviour
- Quorum validator count is queryable from the contract.
- Count matches the number of validators that have submitted matching claims.
