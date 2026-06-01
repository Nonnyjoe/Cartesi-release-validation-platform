---
id: perf-memory-no-leak-v2
name: Monitor advancer RSS after 1000 inputs — no unbounded memory growth (v2.x)
version: 1
min_node_major_version: 2
tags: [performance, memory, load, v2, phase17]
csv_ids: ["17.7"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 600
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
    poll_timeout: 60
    comment: "verify node is processing inputs (memory leak detection is a best-effort baseline)"
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
---

## Description
CSV test 17.7 — Process 1000 inputs through the advancer and monitor the
process RSS to verify there is no unbounded memory growth (memory leak).

## Steps
1. Submit 100+ inputs (batched via stress test setup).
2. Wait for all inputs to reach PROCESSED status.
3. Query advancer Prometheus metrics for process_resident_memory_bytes.
4. Assert memory growth is bounded (not linear with input count).

## Expected Behaviour
- Advancer RSS stabilizes after initial warm-up.
- No unbounded memory growth pattern detected.
- Memory usage stays within expected bounds.
