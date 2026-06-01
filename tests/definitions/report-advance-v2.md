---
id: report-advance-v2
name: Report during advance (v2.x)
version: 1
min_node_major_version: 2
tags: [output, report, vm, v2, phase5]
csv_ids: ["5.11"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0xdeadbeef"
  - type: json_rpc
    method: cartesi_listReports
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 5.11 — Sends any input and verifies the application emits a diagnostic
report during the advance handler.

The student-tracker emits an `advance_processed` report after every advance.
This test verifies that report appears in `cartesi_listReports`.

## Steps
1. Submit payload `0xdeadbeef` via InputBox.addInput.
2. Poll `cartesi_listReports(app)` and assert ≥1 report is returned.

## Expected Behaviour
- chain_tx succeeds.
- cartesi_listReports returns ≥1 report (the advance_processed diagnostic).
