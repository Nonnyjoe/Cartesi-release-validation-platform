---
id: inspect-during-heavy-advance-v2
name: Inspect during heavy advance load — sequential processing (v2.x)
version: 1
min_node_major_version: 2
tags: [inspect, load, concurrency, v2, phase5]
csv_ids: ["5.15"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67222c22686561767922 3a747275657d"
    comment: "trigger heavy CPU-intensive advance"
  - type: inspect_query
    concurrent: 5
    payload: "0x7b22616374696f6e223a22737461747573227d"
    expect_status: 200
---

## Description
CSV test 5.15 — Submit a CPU-heavy advance request, then concurrently send
inspect queries and verify all inspects return correct responses (sequential
processing ensures inspect runs after advance).

## Steps
1. Submit a heavy advance input.
2. Immediately send 5 concurrent inspect requests.
3. Assert all inspect calls return HTTP 200.

## Expected Behaviour
- Inspect requests are queued behind the active advance.
- All inspects return correct state after advance completes.
- No timeouts or crashes during concurrent load.
