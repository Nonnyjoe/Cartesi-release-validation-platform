---
id: cli-create-python-template-v2
name: Execute 'cartesi create --template python' — Python template scaffolded (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, create, template, python, v2, phase1]
csv_ids: ["1.33"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "create my-python-app --template python"
    expect_exit_code: 0
    expect_output_contains: "python"
---

## Description
CSV test 1.33 — Execute `cartesi create --template python` and verify the
Python template is scaffolded correctly with the expected project structure.

## Steps
1. Run `cartesi create my-python-app --template python`.
2. Assert exit code 0.
3. Assert output mentions python template.

## Expected Behaviour
- Python application template is scaffolded.
- Project structure includes Python entrypoint and requirements.
