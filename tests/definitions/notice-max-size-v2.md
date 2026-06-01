---
id: notice-max-size-v2
name: Generate max-size notice (2MB boundary) (v2.x)
version: 1
min_node_major_version: 2
tags: [output, notice, boundary, v2, phase5]
csv_ids: ["5.2"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2267656e65726174655f6c617267655f6e6f74696365227d"
    comment: '{"action":"generate_large_notice"}'
  - type: notice_check
    min_count: 1
    poll_interval: 3
    poll_timeout: 60
---

## Description
CSV test 5.2 — Generate a notice at the 2MB boundary and verify it is stored
and retrievable without truncation.

## Steps
1. Submit an action that generates a ~2MB notice.
2. Assert the notice appears in cartesi_listOutputs.

## Expected Behaviour
- 2MB notice is stored and retrievable in full.
- No OOM or truncation error.
