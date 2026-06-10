# Handover: Persistent Log Capture & Display

**Feature:** Full log capture, persistent storage, and improved dashboard log viewer  
**Status:** Complete — all phases implemented, TypeScript and Python syntax verified clean

---

## Problem Solved

Previously, container logs were streamed live via WebSocket but never written to disk or the database. Once a container stopped — or the browser tab refreshed — all logs were gone. The build process (`cartesi build`), Anvil, the deploy step, and test executor output were completely invisible after the fact. This made debugging failed runs nearly impossible without SSH access.

---

## What Changed

### New file: `services/sandbox-manager/log_buffer.py`
A thread-safe `LogBatchBuffer` class that sits between container log generators and the RabbitMQ publish path. It collects individual log lines from all sources and flushes them in batches (50 lines or every 2 seconds, whichever comes first). This keeps RabbitMQ traffic proportional to log volume rather than emitting one message per line. The buffer is stopped and flushed on sandbox teardown so no lines are lost when containers shut down.

### Modified: `services/sandbox-manager/provisioner.py`
Four changes:
- **All containers are now streamed**, including Anvil, cli-tools, and cannon-deployer. The old exclusion list (`if component in ("anvil", "cannon-deployer", "cli-tools", "")`) is removed.
- **`_stream_service_logs`** routes each line to both the new `log_buffer` (for DB persistence) and the legacy `step_cb` (keeps WebSocket backwards compatibility for any clients expecting the old `service_log` step events).
- **`_build_app_sync`** streams `cartesi build` output in real-time via a daemon thread, and captures `git clone` output after completion. Both are emitted with `source="build"`.
- **`_deploy_app_sync`** emits all `cartesi-rollups-cli deploy` output line-by-line with `source="deploy"`.
- **Teardown** calls `log_buffer.stop()`, which flushes the buffer before containers are removed.

### Modified: `services/sandbox-manager/consumers/sandbox_queue.py`
Creates a `LogBatchBuffer` in `_handle()` backed by a `log_batch_reporter` closure that schedules `_publish_event("log_batch", ...)` on the async event loop. Passes the buffer into `provisioner.provision()`.

### Modified: `services/orchestrator/consumers/sandbox_events.py`
- New `_store_log_batch()` method: bulk-inserts a batch using a single `INSERT ... SELECT FROM jsonb_array_elements(...)` statement — one DB round-trip per batch regardless of how many lines it contains.
- New `log_batch` branch in `_handle()`: stores lines to `orchestrator.run_logs` AND broadcasts them via Redis/WebSocket so connected dashboards receive live updates without waiting for a DB read.

### Modified: `services/orchestrator/models/run.py`
New `RunLog` SQLAlchemy ORM model mapped to `orchestrator.run_logs`. Uses `BigInteger` PK (BIGSERIAL in Postgres) for free chronological ordering and efficient cursor pagination.

### Modified: `services/orchestrator/api/routes/runs.py`
Two new endpoints:
- **`GET /runs/{run_id}/logs`** — cursor-paginated log retrieval with optional `source` (comma-separated), `level` (threshold-based: error/warn/info/debug), `after_id` (cursor), and `limit` (max 500) query params. Returns `{lines: [...], next_cursor: int|null}`.
- **`GET /runs/{run_id}/logs/download`** — streams the full run log as a plain-text file attachment, formatted as `HH:MM:SS [source] LEVEL message`.

### Modified: `services/test-runner/consumers/test_commands.py`
- Wraps `run_test()` in a try/except that captures full Python tracebacks on unhandled executor exceptions.
- Builds a `test_log_lines` list per test: header line, per-assertion pass/fail lines (with `✓`/`✗` indicators), error detail, and a summary footer.
- Calls new `_publish_log_batch()` method which publishes the batch as a `log_batch` event on the `rvp.sandbox` exchange so the orchestrator consumer handles it identically to sandbox logs.

### Modified: `services/dashboard/src/types.ts`
New `RunLogLine` interface: `{ id: number; source: string; level: string; message: string; ts: string }`.

### Modified: `services/dashboard/src/api.ts`
- `runsApi.logs(runId, opts?)` — typed wrapper for `GET /runs/{id}/logs`.
- `runsApi.logsDownloadUrl(runId, source?)` — returns the download URL string for use as an `<a href>`.

### Modified: `services/dashboard/src/pages/RunDetail.tsx`
The old `LiveLogs` component (which received only milestone step events from stored `run_events`) is replaced with a full `LogViewer` component:
- **On mount:** fetches the first 200 lines from `GET /runs/{id}/logs`.
- **Live:** appends `log_batch` WebSocket events in real-time.
- **Source sidebar:** collects unique source labels from loaded lines and renders toggles, each coloured from a fixed palette. Click to filter; "All sources" resets.
- **Level filter:** All / ≥ warn / Error only.
- **Search:** client-side substring filter over loaded lines.
- **Auto-scroll:** on by default; pauses when the user scrolls up, resumes when they scroll back to the bottom.
- **Load more:** appears when `next_cursor` is non-null; fetches the next page of lines.
- **Download:** `📥` link hits the `/logs/download` endpoint directly.
- The **Setup tab** still shows structured milestone step events from `run_events` (unchanged behaviour).

### New migration: `infra/postgres/migrations/0008_run_logs.sql`
```sql
CREATE TABLE orchestrator.run_logs (
    id      BIGSERIAL    PRIMARY KEY,
    run_id  UUID         NOT NULL REFERENCES orchestrator.runs(id) ON DELETE CASCADE,
    source  TEXT         NOT NULL,
    level   TEXT         NOT NULL DEFAULT 'info',
    message TEXT         NOT NULL,
    ts      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_run_logs_run_cursor ON orchestrator.run_logs (run_id, id);
```
Cascade delete means logs are automatically cleaned up when a run is purged.

### Modified: `Makefile`
Added `migrate-logs` target and help entry.

---

## Data Flow (after this change)

```
Container stdout/stderr
  ↓ container.logs(stream=True)  [all containers, incl. Anvil]
  ↓
subprocess output (git clone, cartesi build)
  ↓
exec_run output (cartesi-rollups-cli deploy)
  ↓
test-runner executor diagnostics
  ↓
LogBatchBuffer (50 lines or 2s, whichever first)
  ↓
RabbitMQ: rvp.sandbox exchange → sandbox.events queue
  ↓
Orchestrator sandbox_events consumer
  ├─→ bulk INSERT → orchestrator.run_logs  (persisted forever)
  └─→ Redis pub/sub → WebSocket → Dashboard (live)

Dashboard on page load:
  GET /runs/{id}/logs?limit=200
  → renders LogViewer with source filter + search + download
```

---

## Commands to Run

Run these in order after pulling this branch:

### 1. Apply the database migration
```bash
make migrate-logs
```
This creates `orchestrator.run_logs` and its index. Safe to run against a live DB — uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.

### 2. Rebuild affected images
```bash
make build-orchestrator
make build-sandbox-manager
make build-test-runner
make build-dashboard
```
Or rebuild everything at once:
```bash
make build
```

### 3. Restart services
```bash
make restart
```
Or service by service (keeps infrastructure running):
```bash
make restart-orchestrator
make restart-sandbox-manager
make restart-test-runner
make restart-dashboard
```

### 4. Verify the migration applied
```bash
make shell-db
```
Then inside psql:
```sql
\d orchestrator.run_logs
SELECT COUNT(*) FROM orchestrator.run_logs;
\q
```

### 5. Smoke test
Trigger a new run from the dashboard, then open the run detail page and click the **Logs** tab. You should see log lines appearing live as the sandbox provisions. After the run completes, refresh the page — the logs should still be there.

---

## Notes

- **No breaking changes to existing runs.** Runs that completed before this migration have no `run_logs` rows — the Logs tab will show "No logs captured for this run."
- **Log retention** is not capped. If DB size becomes a concern, a cron job like `DELETE FROM orchestrator.run_logs WHERE run_id IN (SELECT id FROM orchestrator.runs WHERE completed_at < now() - interval '30 days')` can be added later.
- **The `service_log` step event path is kept** as a legacy fallback — any WebSocket client that was processing those events will continue to work. The new `log_batch` event is additive.
- **Anvil logs can be verbose** (one line per block). The `LogBatchBuffer` batching keeps RabbitMQ load manageable; individual lines are capped at 2000 chars before buffering and 4096 chars at DB insert.
