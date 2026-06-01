---
id: security-max-output-size-v2
name: Max output size via JSON-RPC 2MB boundary test (v2.x)
version: 1
min_node_major_version: 2
tags: [security, limits, output-size, v2, phase11]
csv_ids: ["11.8"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2267656e65726174655f6c617267655f6f7574707574227d"
    comment: '{"action":"generate_large_output"} — triggers large notice'
  - type: json_rpc
    method: cartesi_listOutputs
    use_app_address: true
---

## Description
CSV test 11.8 — Verify the JSON-RPC API handles output payloads up to the
2MB limit without truncation or crash.

## Steps
1. Submit an input that causes the application to emit a large output (~2MB).
2. Fetch the output via cartesi_listOutputs.
3. Assert the full payload is returned without corruption.

## Expected Behaviour
- Outputs up to 2MB are returned correctly.
- No truncation or OOM crash occurs.
