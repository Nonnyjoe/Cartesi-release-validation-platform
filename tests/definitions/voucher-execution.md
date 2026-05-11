---
id: voucher-execution
name: Voucher Generation and Execution
version: 1
tags: [voucher, output, core]
release_introduced: v1.4.0
component: authority-claimer
priority: critical
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node
  - graphql
inputs:
  payload: "0xvoucher01"
assertions:
  - type: chain_tx
    payload: "0xvoucher01"
  - type: voucher
    expect_count: 1
  - type: graphql
    query: |
      {
        vouchers {
          edges {
            node {
              index
              destination
              payload
              proof { validity { inputIndexWithinEpoch outputIndexWithinInput } }
            }
          }
        }
      }
    expect:
      path: vouchers.edges[0].node.index
      value: 0
  - type: log_contains
    component: node
    pattern: "voucher"
---

## Description
Tests the full voucher lifecycle: generating a voucher from an application, confirming
it appears in the GraphQL API with a valid Merkle proof, and verifying execution.

## Steps
1. Send an advance-state input with payload `0xvoucher01`. The test dApp is expected
   to emit a voucher in response (requires a voucher-emitting dApp image).
2. Query the voucher via GraphQL and confirm it exists at index 0.
3. Verify the voucher has a valid Merkle proof (proof field is non-null).
4. Confirm the node logs mention "voucher".

## Expected Behaviour
The application processes the input and emits a voucher. The GraphQL API returns the
voucher with a non-null proof once the epoch containing it is closed and a claim
is submitted. Voucher count is exactly 1.

## Notes
This test requires the node image under test to be running a dApp that actually
emits vouchers. A dedicated test dApp (e.g., echo-with-voucher) should be pre-pulled
into the sandbox base image. This is the highest-priority test for verifying the
output pipeline is intact.
