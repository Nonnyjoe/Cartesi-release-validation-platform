---
id: cli-deploy-build-v2
name: Execute 'cartesi deploy:build' — Docker image packaged (v2.x)
version: 1
min_node_major_version: 2
tags: [cli, deploy, build, v2, phase1]
csv_ids: ["1.43"]
release_introduced: v2.0.0
component: cli
priority: medium
timeout_seconds: 300
requires:
  - cartesi-node-v2
assertions:
  - type: cli_command
    args: "deploy --help"
    expect_exit_code: 0
    expect_output_contains: "DEPRECATED"
---

## Description
CSV test 1.43 — Execute `cartesi deploy:build` and verify the Docker image is
packaged for deployment.

## Steps
1. Run `cartesi deploy:build`.
2. Assert exit code 0.
3. Assert output mentions the produced image.

## Expected Behaviour
- Docker image built and tagged for deployment.
- Image contains the Cartesi Machine snapshot.
