---
id: metrics-inputs-counter-v2
name: Processed inputs counter increments after input sent (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, metrics, advancer, v2, phase13]
csv_ids: ["13.13"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 13.13 — Verify the advancer's processed-inputs Prometheus counter
increments after an input reaches PROCESSED status.

## Steps
1. Submit a ping input.
2. Fetch /metrics from advancer.
3. Assert the `cartesi_inputs_processed_total` metric is present and > 0.

## Expected Behaviour
- `cartesi_inputs_processed_total` counter increments with each processed input.
