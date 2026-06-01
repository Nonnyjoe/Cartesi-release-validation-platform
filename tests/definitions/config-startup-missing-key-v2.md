---
id: config-startup-missing-key-v2
name: Missing CARTESI_AUTH_PRIVATE_KEY causes fast-fail startup (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, startup, validation, v2, phase14]
csv_ids: ["14.9"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 60
requires: []
assertions:
  - type: log_contains
    component: claimer
    pattern: "CARTESI_AUTH_PRIVATE_KEY"
    timeout_seconds: 30
    comment: "claimer should fail fast with clear missing-env error"
---

## Description
CSV test 14.9 — Start services without `CARTESI_AUTH_PRIVATE_KEY` set and
verify the node fails fast with a clear missing-environment error.

## Setup
Start sandbox WITHOUT the `CARTESI_AUTH_PRIVATE_KEY` environment variable.

## Steps
1. Start the node without the auth private key.
2. Assert claimer logs mention the missing variable by name.

## Expected Behaviour
- Service fails fast (does not hang waiting for a key).
- Error message clearly names `CARTESI_AUTH_PRIVATE_KEY` as missing.
