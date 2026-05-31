---
id: epoch-close
name: Epoch Close and Claim Submission
version: 1
tags: [epoch, consensus, core]
release_introduced: v1.4.0
component: authority-claimer
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node
  - graphql
inputs:
  payload: "0x65706f63683031"
  blocks_to_advance: 7200
assertions:
  - type: chain_tx
    payload: "0x65706f63683031"
  - type: graphql
    query: |
      { epochs { edges { node { index status } } } }
    expect:
      path: epochs.edges[0].node.status
      value: "CLOSED"
  - type: log_contains
    component: node
    pattern: "epoch closed"
  - type: log_contains
    component: node
    pattern: "claim submitted"
---

## Description
Tests that the authority-claimer component correctly closes an epoch and submits
a claim to the consensus contract after enough blocks have passed.

## Steps
1. Send one advance-state input to create activity in the current epoch.
2. Advance Anvil block time by 7200 blocks (triggering epoch close).
3. Query GraphQL to confirm the epoch status is CLOSED.
4. Check logs for "epoch closed" and "claim submitted".

## Expected Behaviour
After the block advance, the authority-claimer detects the epoch close, generates
the output Merkle tree root, and submits a claim transaction. The GraphQL indexer
reflects the epoch as CLOSED.

## Notes
This test is slow — it waits for the node to process the block advancement.
If "epoch closed" appears but "claim submitted" does not, the claimer component
specifically is broken (not the dispatcher or indexer).
