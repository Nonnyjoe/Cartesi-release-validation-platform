---
id: inspect-state
ai_allowed: true
name: Inspect State REST Endpoint
version: 1
tags: [inspect, core, rest-api]
release_introduced: v1.4.0
component: inspect-server
priority: high
timeout_seconds: 60
requires:
  - cartesi-node
assertions:
  - type: http_status
    endpoint: /inspect/0x
    expect: 200
  - type: http_status
    endpoint: /healthz
    expect: 200
  - type: log_contains
    component: node
    pattern: "inspect request"
---

## Description
Verifies the inspect-state REST endpoint is reachable and returns a valid response
without requiring any on-chain state changes.

## Steps
1. Send a GET to `/inspect/0x` (empty payload inspect).
2. Verify the response is 200.
3. Verify the health check is 200.
4. Check the node logs confirm it handled the inspect request.

## Expected Behaviour
The inspect endpoint responds immediately with 200 and a JSON body. No on-chain
transaction is needed for this test — it purely exercises the REST layer.

## Notes
The inspect server runs on the same port as the node HTTP server. If this fails
but advance-state-basic passes, the inspect-server component specifically is broken.
