---
id: perf-latency-baseline-v2
name: Measure input-to-PROCESSED latency P50 and P99 (v2.x)
version: 1
min_node_major_version: 2
tags: [performance, latency, baseline, v2, phase17]
csv_ids: ["17.4"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 300
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
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 17.4 — Measure the latency from input submission to PROCESSED status,
capturing P50 and P99 percentiles as an alpha baseline for regression detection.

## Steps
1. Submit a ping input and record the submission timestamp.
2. Poll until the input reaches PROCESSED status.
3. Query the advancer Prometheus metrics for duration histograms.

## Expected Behaviour
- P50 latency establishes an alpha performance baseline.
- P99 latency recorded for regression detection in future releases.
- Metrics are exported in Prometheus format.
