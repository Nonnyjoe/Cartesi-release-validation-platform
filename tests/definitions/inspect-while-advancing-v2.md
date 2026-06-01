---
id: inspect-while-advancing-v2
name: Inspect while advance is actively processing — queued correctly (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, concurrency, v2, phase15]
csv_ids: ["15.8"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a22736c65657022 2c226d73223a323030 307d"
    comment: "slow advance that takes ~2s — submit inspect during it"
  - type: inspect_query
    payload: "0x7b22616374696f6e223a22737461747573227d"
    expect_status: 200
    poll_timeout: 60
---

## Description
CSV test 15.8 — Submit a slow advance input, then immediately fire an inspect
query and verify the inspect is queued and returns after the advance completes.

## Steps
1. Submit an advance input that takes 2+ seconds to process.
2. Immediately send an inspect query.
3. Assert inspect returns HTTP 200 (after being queued).

## Expected Behaviour
- Inspect is queued while advance is in progress.
- Inspect returns the correct state after advance completes.
- No timeout or race condition errors.
