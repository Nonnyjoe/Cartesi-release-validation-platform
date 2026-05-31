---
id: voucher-generation-v2
name: Voucher Generation (v2.x)
version: 1
min_node_major_version: 2
tags: [voucher, output, generation, core, v2]
release_introduced: v2.0.0
component: advancer
priority: critical
timeout_seconds: 240
requires:
  - anvil
  - cartesi-node-v2
  - voucher-emitting-app
assertions:
  - type: chain_tx
    payload: "0x7663687231"
  - type: voucher_v2
    mode: generate
    expect_count: 1
    poll_interval: 3
    poll_timeout: 120
---

## Description
Sends an input that should cause the loaded Cartesi application to emit a voucher,
then polls `cartesi_listOutputs` until a voucher-type output appears.

## Steps
1. Submit payload `0x7663687231` ("vchr1") via `InputBox.addInput` on Anvil.
2. Poll `cartesi_listOutputs(app_address)` every 3 s for up to 120 s.
3. Assert at least 1 output of type `Voucher` is returned.

## Expected Behaviour
- The `chain_tx` succeeds (receipt status=1).
- `cartesi_listOutputs` returns a voucher-type output within 120 s.
- The voucher's `destination` and `payload` fields are populated.

## Notes
Requires a voucher-emitting Cartesi machine snapshot in the `rvp-test-snapshot`
Docker volume.  A standard echo app emits Notices, not Vouchers — you must use a
dedicated test application (e.g. echo-with-voucher, student-tracker with a
withdraw trigger, or a custom voucher-emitting dApp).

The payload `0x7663687231` is a conventional "voucher trigger" signal.  The
loaded application must recognise this payload and emit at least one voucher.

The proof field will be null at this stage (epoch not yet claimed) — that is
expected behaviour; `voucher-execution-v2` tests proof availability and on-chain
execution separately.
