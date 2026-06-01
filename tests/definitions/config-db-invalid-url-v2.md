---
id: config-db-invalid-url-v2
name: Invalid CARTESI_DATABASE_CONNECTION URL fails fast (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, startup, database, v2, phase14]
csv_ids: ["14.11"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 60
env_overrides:
  CARTESI_DATABASE_CONNECTION: "postgres://invalid:5432/nonexistent"
requires: []
assertions:
  - type: log_contains
    component: advancer
    pattern: "database"
    timeout_seconds: 30
    comment: "advancer should fail fast with DB connection error"
---

## Description
CSV test 14.11 — Set `CARTESI_DATABASE_CONNECTION` to an invalid URL and verify
services fail fast with a clear DB connection error.

## Setup
Start sandbox with an invalid database connection URL.

## Steps
1. Start the advancer with an invalid DB URL.
2. Assert advancer logs a database connection error.

## Expected Behaviour
- Service fails fast (within 30s).
- Error message mentions the database connection failure.
- No silent hang or infinite retry loop.
