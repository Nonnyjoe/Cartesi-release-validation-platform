---
id: consensus-unauthorized-claim-v2
name: Submit claim from unauthorized validator — reverts (v2.x)
version: 1
min_node_major_version: 2
tags: [cloud, consensus, security, v2, phase10]
csv_ids: ["10.6"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x"
    comment: "submit an input to verify the node accepts transactions"
---

## Description
CSV test 10.6 — Attempt to submit a claim to the Authority contract from an
address that is not a registered validator, and verify the transaction reverts.

## Steps
1. Attempt to call Authority.submitClaim() from a non-validator account.
2. Assert the transaction reverts.

## Expected Behaviour
- Unauthorized validator claim attempt reverts on-chain.
- Authority contract enforces the validator whitelist.
