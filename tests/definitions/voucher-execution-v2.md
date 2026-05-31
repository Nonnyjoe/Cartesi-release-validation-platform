---
id: voucher-execution-v2
name: Voucher Execution (v2.x)
version: 1
min_node_major_version: 2
tags: [voucher, output, execution, core, v2]
release_introduced: v2.0.0
component: claimer
priority: critical
timeout_seconds: 360
requires:
  - anvil
  - cartesi-node-v2
  - claimer
  - voucher-emitting-app
assertions:
  - type: chain_tx
    payload: "0x7663687231"
  - type: voucher_v2
    mode: execute
    expect_count: 1
    poll_interval: 5
    poll_timeout: 240
---

## Description
Full voucher lifecycle test for v2.x: triggers a voucher via an on-chain input,
waits for the epoch to be closed and claimed (so a Merkle proof is available),
then executes the voucher on-chain by calling `CartesiDApp.executeVoucher`.

## Steps
1. Submit payload `0x7663687231` ("vchr1") via `InputBox.addInput` on Anvil.
2. Poll `cartesi_listOutputs(app_address)` until a voucher with a non-null `proof`
   appears — this requires the claimer to have submitted the epoch claim.
3. Call `CartesiDApp.executeVoucher(destination, payload, proof)` via a Foundry
   container sharing the Anvil network namespace.
4. Assert the transaction receipt status is 1 (success).

## Expected Behaviour
- The `chain_tx` succeeds (receipt status=1).
- `cartesi_listOutputs` eventually returns a voucher with a populated `proof`
  object (validator + claimer have processed the epoch).
- `executeVoucher` on the CartesiDApp contract succeeds — the destination contract
  receives the call encoded in the voucher payload.

## Notes
Requires:
  - A voucher-emitting Cartesi machine snapshot in `rvp-test-snapshot`.
  - `CARTESI_EPOCH_LENGTH=1` (default in sandbox provisioner) so the epoch closes
    quickly after the input is processed.
  - The claimer service to be running and able to submit the claim to the
    `CartesiDApp` contract on Anvil.

Proof encoding: the `executeVoucher` call ABI-encodes the `OutputValidityProof`
struct (6 scalar fields + 2 dynamic bytes32[] siblings arrays) together with the
`context` bytes, matching the rollups-contracts v2.x CartesiDApp interface.

If the claimer does not run (e.g. the Cartesi machine snapshot is missing), the
proof will never appear and the test will time out with a clear diagnostic message.
