---
id: cli-create-rust-template-v2
name: Execute 'cartesi create --template rust' — Rust template scaffolded (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, create, template, rust, v2, phase1]
csv_ids: ["1.35"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 60
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "create my-rust-app --template rust"
    expect_exit_code: 0
    expect_output_contains: "rust"
---

## Description
CSV test 1.35 — Execute `cartesi create --template rust` and verify the Rust
template is scaffolded correctly.

## Steps
1. Run `cartesi create my-rust-app --template rust`.
2. Assert exit code 0.
3. Assert output confirms rust template used.

## Expected Behaviour
- Rust application template scaffolded.
- Project includes Cargo.toml and Rust entrypoint.
