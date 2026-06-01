---
id: multi-app-restart-v2
name: Restart node with multiple apps — all apps resume correctly (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, multi-app, cloud, restart, v2, phase10]
csv_ids: ["10.3"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 360
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: service_restart
    service: advancer
    wait_healthy: true
    timeout: 90
  - type: json_rpc
    method: cartesi_listApplications
    expect_count: 2
---

## Description
CSV test 10.3 — With two registered apps, restart the node and verify both
apps resume processing correctly from their saved state.

## Steps
1. Register two apps and submit inputs to each.
2. Restart the advancer.
3. Assert both apps are still registered and healthy.

## Expected Behaviour
- Both apps resume from their last checkpointed state.
- No inputs are lost or double-processed.
