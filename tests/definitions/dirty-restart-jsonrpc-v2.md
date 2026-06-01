---
id: dirty-restart-jsonrpc-v2
name: Restart jsonrpc-api with populated database — serves history correctly (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, dirty-restart, jsonrpc, standalone, persistence, v2, phase9]
csv_ids: ["9.2"]
release_introduced: v2.0.0
component: jsonrpc
priority: high
timeout_seconds: 180
group: dirty_restart
suite_ids: [dirty_restart]
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a227265676973746572227d"
    comment: "create a notice before restart"
  - type: service_restart
    service: jsonrpc
    verify_path: /readyz
    verify_timeout: 60
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 9.2 — Restart jsonrpc-api after inputs have been processed and verify
the existing history is correctly served from the database.

## Steps
1. Submit a register action to create history.
2. Restart the jsonrpc container.
3. After recovery, call cartesi_listInputs and verify history is intact.

## Expected Behaviour
- Existing inputs and outputs remain accessible after restart.
- No data loss from the populated database.
