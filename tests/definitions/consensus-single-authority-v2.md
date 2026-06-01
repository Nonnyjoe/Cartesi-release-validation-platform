---
id: consensus-single-authority-v2
name: Deploy with single-validator Authority consensus (v2.x)
version: 1
min_node_major_version: 2
tags: [cloud, consensus, authority, v2, phase10]
csv_ids: ["10.4"]
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
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
  - type: log_contains
    component: claimer
    pattern: "claim"
    timeout_seconds: 120
---

## Description
CSV test 10.4 — Deploy an application using the default single-validator
Authority contract and verify the claim submission works correctly.

## Steps
1. Submit a ping input.
2. Assert input is processed.
3. Assert claimer generates and submits a claim.

## Expected Behaviour
- Application runs with single-validator Authority consensus.
- Claim is submitted by the sole validator.
- Epoch advances and is settled correctly.
