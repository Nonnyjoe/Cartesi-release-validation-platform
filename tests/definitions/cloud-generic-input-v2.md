---
id: cloud-generic-input-v2
name: Send valid generic payload (cloud/sandbox) (v2.x)
version: 1
min_node_major_version: 2
tags: [input, generic, cloud, sandbox, v2, phase4]
csv_ids: ["4.1"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 90
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
---

## Description
CSV test 4.1 — Send a valid generic payload in cloud/sandbox mode and verify
basic payload handling on the live infrastructure.

## Steps
1. Submit a generic ping payload.
2. Assert the input is indexed.

## Expected Behaviour
- Input is indexed and processed on sandbox (cloud proxy) infrastructure.
