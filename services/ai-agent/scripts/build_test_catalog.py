"""Generate the test catalog markdown the agent reads at session start.

Reads tests.definitions WHERE is_active AND ai_allowed=true and writes a structured markdown
list to context/sources/project/test-catalog.md. Idempotent; safe to run on every container
restart.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg

OUT_PATH = Path(__file__).resolve().parent.parent / "context" / "sources" / "project" / "test-catalog.md"


def _override_keys_for(parsed: dict) -> list[str]:
    """Surface the leaf-level keys the agent can override via parameter_overrides."""
    keys: set[str] = set()
    for assertion in parsed.get("assertions", []) or []:
        if not isinstance(assertion, dict):
            continue
        for k, v in assertion.items():
            if k == "type":
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                keys.add(k)
    return sorted(keys)


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
            SELECT slug, name, tags, component, priority, definition_parsed
            FROM tests.definitions
            WHERE is_active = true AND ai_allowed = true
            ORDER BY component NULLS LAST, slug
            """,
        )
    finally:
        await conn.close()

    lines: list[str] = []
    lines.append("# Whitelisted Test Catalog (auto-generated)")
    lines.append("")
    lines.append(
        "These tests are flagged `ai_allowed: true` and may be invoked via the `trigger_test` "
        "tool. For each one, you can pass `parameter_overrides` to change inputs.",
    )
    lines.append("")

    if not rows:
        lines.append("_No whitelisted tests yet._")
    else:
        current_component = None
        for r in rows:
            comp = r["component"] or "uncategorized"
            if comp != current_component:
                lines.append(f"## {comp}")
                lines.append("")
                current_component = comp
            slug = r["slug"]
            name = r["name"]
            tags = r["tags"] or []
            parsed_val = r["definition_parsed"]
            if isinstance(parsed_val, str):
                parsed_val = json.loads(parsed_val)
            override_keys = _override_keys_for(parsed_val or {})
            tag_str = ", ".join(tags) if tags else "—"
            override_str = ", ".join(f"`{k}`" for k in override_keys) if override_keys else "—"
            lines.append(f"- **`{slug}`** — {name}")
            lines.append(f"  - tags: {tag_str}")
            lines.append(f"  - override keys: {override_str}")
        lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT_PATH} ({len(rows)} tests)")


if __name__ == "__main__":
    asyncio.run(main())
