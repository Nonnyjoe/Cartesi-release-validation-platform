---
id: security-large-dependency-v2
name: Deploy dApp with massive build dependencies — storage limits (v2.x)
version: 1
min_node_major_version: 2
tags: [security, limits, v2, phase11]
csv_ids: ["11.2"]
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
CSV test 11.2 — Deploy a dApp with a large rootfs containing massive build
dependencies to test storage limit handling in the Cartesi Machine.

## Steps
1. Submit an input to the dApp with heavy dependencies loaded.
2. Assert the input is processed successfully.
3. Assert the advancer remains healthy (no OOM or crash).

## Expected Behaviour
- dApp with large dependencies runs within VM storage limits.
- No host-side storage exhaustion.
- Advancer remains healthy throughout.
