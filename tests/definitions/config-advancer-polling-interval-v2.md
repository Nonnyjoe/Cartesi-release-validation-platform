---
id: config-advancer-polling-interval-v2
name: CARTESI_ADVANCER_POLLING_INTERVAL custom value — timing observed (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, advancer, v2, phase14]
csv_ids: ["14.4"]
release_introduced: v2.0.0
component: advancer
priority: low
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_ADVANCER_POLLING_INTERVAL: "5s"
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
    poll_timeout: 60
---

## Description
CSV test 14.4 — Set `CARTESI_ADVANCER_POLLING_INTERVAL=5s` (slower than
default) and verify the advancer uses the custom polling interval.

## Setup
Start sandbox with `CARTESI_ADVANCER_POLLING_INTERVAL=5s`.

## Steps
1. Submit a ping input.
2. Assert input is eventually processed (at the slower poll rate).

## Expected Behaviour
- Advancer polls every 5 seconds instead of the default.
- Input processing is delayed but still correct.
