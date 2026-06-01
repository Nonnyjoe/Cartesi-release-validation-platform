---
id: cli-doctor-docker-down-v2
name: Execute 'cartesi doctor' with Docker stopped — identifies missing requirements (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cli, doctor, v2, phase1]
csv_ids: ["1.2"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 30
requires: []
assertions:
  - type: cli_command
    args: "doctor"
    expect_exit_code: 0
    expect_output_contains: "Docker"
---

## Description
CSV test 1.2 — Run `cartesi doctor` in an environment where Docker is not
accessible and verify it reports the missing requirement clearly.

## Setup
This test must run without Docker socket access (not available in requires).

## Steps
1. Run `cartesi doctor` without Docker running.
2. Assert non-zero exit code.
3. Assert output mentions "Docker" as missing.

## Expected Behaviour
- doctor identifies Docker as missing.
- Clear error message directs user to install/start Docker.
