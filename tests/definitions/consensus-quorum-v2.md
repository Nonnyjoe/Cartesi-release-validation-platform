---
id: consensus-quorum-v2
name: Deploy with multi-validator Quorum (N-of-M consensus) (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cloud, consensus, quorum, v2, phase10]
csv_ids: ["10.5"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: log_contains
    component: claimer
    pattern: "quorum"
    timeout_seconds: 120
---

## Description
CSV test 10.5 — Deploy an application using a multi-validator Quorum consensus
contract (N-of-M validators must agree) and verify the consensus mechanism.

## Setup
This test requires a sandbox configured with QuorumFactory deployment.

## Steps
1. Deploy with Quorum consensus (2-of-3 validators).
2. Submit a ping input.
3. Assert claimer mentions quorum in logs.

## Expected Behaviour
- Quorum consensus requires N validators to agree on a claim.
- N-of-M threshold enforced on-chain.
