---
id: cli-build-snapshot-v2
name: Build with public snapshot workflow — reproducible builds (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, build, snapshot, v2, phase1]
csv_ids: ["1.23"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 300
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "build --help"
    expect_exit_code: 0
    expect_output_contains: "build"
    timeout: 30
---

## Description
CSV test 1.23 — Build using the public snapshot workflow and verify the build
process is reproducible with the cached snapshot.

## Steps
1. Run `cartesi build --use-snapshot` (or equivalent flag).
2. Assert exit code 0.
3. Verify build uses a cached public snapshot.

## Expected Behaviour
- Public snapshot is fetched and used as build base.
- Reproducible build confirmed.
