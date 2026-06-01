---
id: config-auth-private-key-v2
name: CARTESI_AUTH_KIND=private-key — private-key auth path used (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, auth, v2, phase14]
csv_ids: ["14.12"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_AUTH_KIND: "private-key"
assertions:
  - type: health_check
    service: claimer
    path: /readyz
    expect_status: 200
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: log_contains
    service: claimer
    text: "private"
    timeout_seconds: 60
---

## Description
CSV test 14.12 — Explicitly set `CARTESI_AUTH_KIND=private-key` and verify
the private-key auth path is used for signing claim transactions.

## Setup
Start sandbox with `CARTESI_AUTH_KIND=private-key`.

## Steps
1. Verify claimer is healthy.
2. Submit a ping input to trigger claim processing.
3. Assert claimer logs mention private-key auth.

## Expected Behaviour
- Private-key auth path is explicitly activated.
- Claim signing uses the configured private key.
