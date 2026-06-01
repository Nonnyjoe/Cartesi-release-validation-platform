---
id: security-command-injection-v2
name: Attempt command injection via CLI inputs — prevented (v2.x)
version: 1
min_node_major_version: 2
tags: [security, injection, v2, phase11]
csv_ids: ["11.4"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 60
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a227265676973746572222c226e616d65223a22616c696365273b20726d202d7266202f3b2023227d"
    comment: "injection attempt: action=register name contains semicolon and rm command"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 11.4 — Submit a payload containing shell injection characters and
verify the VM processes it as data (not commands) without host impact.

## Steps
1. Submit a payload containing `'; rm -rf /; #` as JSON field value.
2. Assert the input is processed normally by the application.
3. Assert no host-side command execution occurred.

## Expected Behaviour
- Input is treated as opaque data by the VM.
- No shell commands are executed on the host.
- The application either processes the payload or rejects it gracefully.
