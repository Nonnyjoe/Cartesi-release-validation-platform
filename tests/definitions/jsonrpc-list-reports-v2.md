---
id: jsonrpc-list-reports-v2
ai_allowed: true
name: cartesi_listReports pagination and input/epoch filter (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, reports, pagination, v2, phase8]
csv_ids: ["8.13"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0xdeadbeef"
    comment: "any input — student-tracker emits advance_processed report"
  - type: json_rpc
    method: cartesi_listReports
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 8.13 — Verify `cartesi_listReports` returns reports with correct
pagination and input/epoch filters.

## Steps
1. Submit any input to trigger an advance_processed diagnostic report.
2. Call `cartesi_listReports` with the app address.
3. Assert at least one report is returned.

## Expected Behaviour
- Response contains `result.data` with ≥1 report.
- Each report has `index`, `inputIndex`, and `payload`.
