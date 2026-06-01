---
id: cli-create-app-v2
name: Execute 'cartesi create' — scaffolds new app directory (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, create, v2, phase1]
csv_ids: ["1.3"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "create my-test-app --template javascript"
    expect_exit_code: 0
    expect_output_contains: "created"
---

## Description
CSV test 1.3 — Execute `cartesi create my-test-app` and verify it scaffolds
a new application directory with the expected structure.

## Steps
1. Run `cartesi create my-test-app`.
2. Assert exit code 0.
3. Assert output mentions the new app name.

## Expected Behaviour
- New app directory scaffolded successfully.
- Output confirms the app directory name and template used.
