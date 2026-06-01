---
id: cli-create-javascript-template-v2
name: Execute 'cartesi create --template javascript' — JS template scaffolded (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, create, template, javascript, v2, phase1]
csv_ids: ["1.34"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "create my-js-app --template javascript"
    expect_exit_code: 0
    expect_output_contains: "created"
---

## Description
CSV test 1.34 — Execute `cartesi create --template javascript` and verify the
JavaScript template is scaffolded with the expected project structure.

## Steps
1. Run `cartesi create my-js-app --template javascript`.
2. Assert exit code 0.
3. Assert output mentions javascript template.

## Expected Behaviour
- JavaScript application template scaffolded.
- Project includes package.json and JS entrypoint.
