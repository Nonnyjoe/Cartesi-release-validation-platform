---
id: security-vm-ram-limit-v2
name: dApp consuming 100% VM RAM — graceful crash/log (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, security, limits, vm, v2, phase11]
csv_ids: ["11.1"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2265786861757374535f72616d227d"
    comment: '{"action":"exhaust_ram"} — triggers VM RAM exhaustion'
  - type: log_contains
    service: advancer
    text: "exception"
    timeout_seconds: 60
---

## Description
CSV test 11.1 — Deploy a dApp that exhausts 100% of VM RAM and verify the
host system is protected (graceful crash, logged error, no host OOM).

## Steps
1. Submit a payload that causes the VM to exhaust its RAM.
2. Assert the advancer logs an exception or error.
3. Assert the host is not affected (node restarts cleanly, host stable).

## Expected Behaviour
- VM crashes with an OOM/exception error.
- Error is logged by the advancer.
- Host system and other services remain unaffected.
