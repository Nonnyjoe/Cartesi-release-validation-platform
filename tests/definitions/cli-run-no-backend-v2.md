---
id: cli-run-no-backend-v2
name: Execute 'cartesi run --no-backend' — starts without bundler (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, run, v2, phase1]
csv_ids: ["1.27"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "run --dry-run"
    expect_exit_code: 0
    timeout: 90
  - type: health_check
    service: jsonrpc
    path: /readyz
    expect_status: 200
---

## Description
CSV test 1.27 — Execute `cartesi run --no-backend` and verify the node starts
without the bundler/explorer containers.

## Steps
1. Run `cartesi run --dry-run`.
2. Assert exit code 0.
3. Assert core services (jsonrpc) are healthy.

## Expected Behaviour
- Node starts without optional backend services.
- Core services are healthy.
- Bundler/explorer containers are not started.
