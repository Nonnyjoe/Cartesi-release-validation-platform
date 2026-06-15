"""Generate the test catalog markdown the agent reads at session start.

The catalog now covers the full Tests-section inventory (~250 ai_allowed tests),
so it is deliberately COMPACT: a phase-grouped slug list, no per-test detail.
The agent loads any test's full definition on demand via `read_test_definition`;
manual sessions additionally receive their selected tests (with names) in the
work-plan message.

Reads tests.definitions WHERE is_active AND ai_allowed=true and writes
context/sources/project/test-catalog.md. Idempotent; safe to run on every
container restart.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

OUT_PATH = Path(__file__).resolve().parent.parent / "context" / "sources" / "project" / "test-catalog.md"


async def main() -> None:
    dsn = os.environ.get("DATABASE_URL_PG")
    if not dsn:
        # Fall back to converting the SQLAlchemy DSN
        sa = os.environ.get("DATABASE_URL", "")
        dsn = sa.replace("postgresql+asyncpg://", "postgresql://")
    if not dsn:
        print("DATABASE_URL not set; cannot generate test catalog", file=sys.stderr)
        return

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            """
            SELECT COALESCE(phase, 'Unphased') AS phase, slug
            FROM tests.definitions
            WHERE is_active = true AND ai_allowed = true
            ORDER BY phase, slug
            """,
        )
    finally:
        await conn.close()

    lines: list[str] = []
    lines.append("# Test Catalog (auto-generated, phase-grouped)")
    lines.append("")
    lines.append(
        "Every test below is runnable by the agent. In MANUAL sessions you execute "
        "them yourself with primitive tools; in runner sessions you may delegate via "
        "`trigger_test`. Load any test's full definition (steps, assertions, expected "
        "behaviour, override keys) with `read_test_definition(slug)` — do that before "
        "executing a test, never guess its contents."
    )
    lines.append("")

    if not rows:
        lines.append("_No runnable tests yet._")
    else:
        current_phase = None
        bucket: list[str] = []

        def _flush():
            if bucket:
                # Comma-joined slugs keep the catalog ~10x smaller than list items.
                lines.append(", ".join(f"`{s}`" for s in bucket))
                lines.append("")
                bucket.clear()

        for r in rows:
            if r["phase"] != current_phase:
                _flush()
                current_phase = r["phase"]
                lines.append(f"## {current_phase}")
                lines.append("")
            bucket.append(r["slug"])
        _flush()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT_PATH} ({len(rows)} tests)")


if __name__ == "__main__":
    asyncio.run(main())
