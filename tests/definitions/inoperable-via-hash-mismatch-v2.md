---
id: inoperable-via-hash-mismatch-v2
name: Trigger app INOPERABLE via VM hash mismatch (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, recovery, inoperable, hash-check, v2, phase9]
csv_ids: ["9.21"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: log_contains
    component: advancer
    pattern: "INOPERABLE"
    comment: "verify INOPERABLE state appears in logs when hash check fails"
---

## Description
CSV test 9.21 — Trigger the application INOPERABLE state by deploying a
snapshot with a hash that does not match the on-chain registration.

This test requires a sandbox started with a deliberately mismatched machine hash
and `CARTESI_FEATURE_MACHINE_HASH_CHECK_ENABLED=true` (the default).

## Steps
1. Start the sandbox with a snapshot whose hash differs from the registered hash.
2. Submit any input.
3. Assert the advancer logs contain "INOPERABLE".

## Expected Behaviour
- Advancer detects hash mismatch.
- App transitions to INOPERABLE terminal state.
- No further inputs are processed.
