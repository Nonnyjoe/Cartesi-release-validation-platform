---
id: multi-app-fair-scheduling-v2
name: Heavy app does not starve light app — fair scheduling regression (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, multi-app, cloud, performance, v2, phase10]
csv_ids: ["10.2"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a22686561767922 2c22637963 6c6573223a 31303030303030 30307d"
    comment: "heavy workload input to app 1"
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
    comment: "light input to app 2 — must not be starved"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
    poll_timeout: 60
---

## Description
CSV test 10.2 — Bug 2 regression: verify that a CPU-heavy app processing large
inputs does not starve a lighter app from being advanced.

## Steps
1. Submit a CPU-heavy input to app 1.
2. Immediately submit a light ping to app 2.
3. Assert app 2's input is processed within a reasonable time.

## Expected Behaviour
- Scheduler does not give app 1 exclusive CPU access.
- App 2 is advanced within the expected time window.
- Bug 2 regression confirmed: no starvation observed.
