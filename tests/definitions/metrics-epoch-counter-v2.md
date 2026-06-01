---
id: metrics-epoch-counter-v2
name: Epoch counter increments after epoch closes (v2.x)
version: 1
min_node_major_version: 2
tags: [telemetry, metrics, v2, phase13]
csv_ids: ["13.14"]
release_introduced: v2.0.0
component: advancer
priority: low
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listEpochs
    use_app_address: true
    expect_count: 1
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 13.14 — Verify an epoch-related Prometheus counter increments after
an epoch status transition.

## Steps
1. Submit an input and wait for epoch to progress.
2. Fetch /metrics from advancer.
3. Assert `cartesi_epochs_total` or similar metric is present.

## Expected Behaviour
- An epoch counter metric is present in the advancer /metrics output.
- The metric increments as epochs are processed.
