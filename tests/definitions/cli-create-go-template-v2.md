---
id: cli-create-go-template-v2
name: Execute 'cartesi create --template go' — Go template scaffolded (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, create, template, go, v2, phase1]
csv_ids: ["1.36"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "create my-go-app --template go"
    expect_exit_code: 0
    expect_output_contains: "go"
---

## Description
CSV test 1.36 — Execute `cartesi create --template go` and verify the Go
template is scaffolded with the expected project structure.

## Steps
1. Run `cartesi create my-go-app --template go`.
2. Assert exit code 0.
3. Assert output confirms go template used.

## Expected Behaviour
- Go application template scaffolded.
- Project includes go.mod and Go entrypoint.
