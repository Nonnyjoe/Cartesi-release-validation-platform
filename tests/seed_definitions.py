#!/usr/bin/env python3
"""
tests/seed_definitions.py
Reads all .md files in tests/definitions/ and upserts them into tests.definitions.
Run once after the DB is up:
  python tests/seed_definitions.py
"""
import asyncio
import os
import re
import sys
import uuid
import json
from pathlib import Path

import asyncpg
import yaml

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://rvp:changeme@localhost:5432/rvp"
)

DEFS_DIR = Path(__file__).parent / "definitions"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_md(path: Path) -> dict:
    raw = path.read_text()
    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError(f"{path}: no YAML frontmatter found")
    meta = yaml.safe_load(match.group(1))
    meta["body"] = raw[match.end():].strip()
    return raw, meta


async def seed():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        files = sorted(DEFS_DIR.glob("*.md"))
        print(f"Seeding {len(files)} definition(s)...")

        for f in files:
            raw, meta = parse_md(f)
            slug   = meta["id"]
            name   = meta["name"]
            version = int(meta.get("version", 1))
            tags   = meta.get("tags", [])
            component = meta.get("component")
            priority  = meta.get("priority", "medium")
            timeout   = int(meta.get("timeout_seconds", 120))
            release   = meta.get("release_introduced")

            # Remove body from parsed JSON (it's a UI convenience field)
            parsed = {k: v for k, v in meta.items() if k != "body"}

            await conn.execute("""
                INSERT INTO tests.definitions
                  (id, slug, name, version, tags, component, priority,
                   timeout_seconds, release_introduced, definition_raw, definition_parsed,
                   is_active, created_by)
                VALUES
                  ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, true, 'seed')
                ON CONFLICT (slug) DO UPDATE SET
                  name=EXCLUDED.name,
                  version=EXCLUDED.version,
                  tags=EXCLUDED.tags,
                  component=EXCLUDED.component,
                  priority=EXCLUDED.priority,
                  timeout_seconds=EXCLUDED.timeout_seconds,
                  definition_raw=EXCLUDED.definition_raw,
                  definition_parsed=EXCLUDED.definition_parsed,
                  updated_at=now()
            """,
                str(uuid.uuid4()), slug, name, version,
                tags, component, priority, timeout, release,
                raw, json.dumps(parsed),
            )
            print(f"  ✓ {slug}")

        print("Seed complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
