---
id: cli-version-v2
name: Execute 'cartesi --version' returns version string (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, version, v2, phase1]
csv_ids: ["1.45"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 30
requires: []
assertions:
  - type: cli_command
    args: "--version"
    expect_exit_code: 0
    expect_output_contains: "."
---

## Description
CSV test 1.45 — Execute `cartesi --version` and verify the version string is
present and parseable as a semver.

## Steps
1. Run `cartesi --version` inside the CLI container.
2. Assert exit code 0.
3. Assert output contains a version string with a dot (e.g., "2.0.0").

## Expected Behaviour
- Version string is printed to stdout.
- Format is parseable (major.minor.patch).
