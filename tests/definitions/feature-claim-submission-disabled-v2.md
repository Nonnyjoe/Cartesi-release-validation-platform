---
id: feature-claim-submission-disabled-v2
name: CARTESI_FEATURE_CLAIM_SUBMISSION_ENABLED=false puts claimer in read-only mode (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, feature-flag, claimer, read-only, v2, phase9]
csv_ids: ["9.20"]
release_introduced: v2.0.0
component: claimer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_FEATURE_CLAIM_SUBMISSION_ENABLED: "false"
assertions:
  - type: health_check
    service: claimer
    path: /readyz
    expect_status: 200
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 9.20 — When `CARTESI_FEATURE_CLAIM_SUBMISSION_ENABLED=false`, the
claimer should process epochs but skip L1 claim submissions.

## Setup
This test requires the sandbox to be started with:
```
CARTESI_FEATURE_CLAIM_SUBMISSION_ENABLED=false
```

## Steps
1. Start node with claim submission disabled.
2. Verify claimer is still healthy (just read-only).
3. Submit an input and confirm it is still indexed.

## Expected Behaviour
- Claimer starts and remains healthy.
- No L1 transactions are sent for claims.
- Inputs and outputs are still processed normally.
