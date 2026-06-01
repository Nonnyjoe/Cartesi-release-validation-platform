---
id: multi-app-two-apps-v2
name: Deploy two apps on same node — multi-app support (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, multi-app, cloud, v2, phase10]
csv_ids: ["10.1"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67222c2261707022 3a2231227d"
    comment: "input to app 1"
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67222c2261707022 3a2232227d"
    comment: "input to app 2"
  - type: json_rpc
    method: cartesi_listApplications
    expect_count: 2
---

## Description
CSV test 10.1 — Deploy two separate applications on the same node instance
and verify both are registered and process inputs independently.

## Steps
1. Register two app addresses with the node.
2. Submit inputs to each app.
3. Assert both apps appear in cartesi_listApplications.

## Expected Behaviour
- Node manages both apps concurrently.
- Each app's state is isolated from the other.
