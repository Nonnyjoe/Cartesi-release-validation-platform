---
id: feature-machine-hash-check-disabled-v2
name: CARTESI_FEATURE_MACHINE_HASH_CHECK_ENABLED=false bypasses VM hash mismatch (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, feature-flag, hash-check, dev-mode, v2, phase9]
csv_ids: ["9.18"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_FEATURE_MACHINE_HASH_CHECK_ENABLED: "false"
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 9.18 — When `CARTESI_FEATURE_MACHINE_HASH_CHECK_ENABLED=false`, the
advancer should process inputs even if the stored machine hash does not match the
snapshot hash (dev/CI mode bypass).

## Setup
This test requires the sandbox to be started with:
```
CARTESI_FEATURE_MACHINE_HASH_CHECK_ENABLED=false
```

## Steps
1. Start node with hash check disabled.
2. Submit a ping input.
3. Assert the input is processed (no INOPERABLE state triggered).

## Expected Behaviour
- Inputs are processed regardless of machine hash mismatches.
- Useful for CI environments where the snapshot may differ from the build hash.
