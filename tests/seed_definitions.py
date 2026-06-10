#!/usr/bin/env python3
"""
tests/seed_definitions.py
Reads all .md files in tests/definitions/ and upserts them into tests.definitions.
Run once after the DB is up:
  python tests/seed_definitions.py
"""
import asyncio
import csv
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
CSV_PATH = Path(__file__).parent.parent / "cartesi-sdk-v2-qa.csv"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Fallback: map phaseN tag → canonical phase name when csv_ids is absent
_PHASE_TAG_NAMES = {
    "phase1":  "Phase 1: Environment",
    "phase2":  "Phase 2: Clean Restarts",
    "phase3":  "Phase 3: Inputs (Local)",
    "phase4":  "Phase 4: Inputs (Remote)",
    "phase5":  "Phase 5: VM Outputs",
    "phase6":  "Phase 6: Voucher Execution",
    "phase7":  "Phase 7: Token Portals",
    "phase8":  "Phase 8: Persistence & Recovery",
    "phase9":  "Phase 9: Chaos & Fault Tolerance",
    "phase10": "Phase 10: Multi-App & Consensus",
    "phase11": "Phase 11: Security & Limits",
    "phase12": "Phase 12: Internal CLI",
    "phase13": "Phase 13: Telemetry & Health",
    "phase14": "Phase 14: Configuration",
    "phase15": "Phase 15: Inspect Service",
    "phase16": "Phase 16: PRT - Dispute Protocol",
    "phase17": "Phase 17: Performance & Load",
}


def _load_csv_lookup() -> dict[str, tuple[str, str]]:
    """Return {csv_id → (phase, category)} from cartesi-sdk-v2-qa.csv."""
    lookup: dict[str, tuple[str, str]] = {}
    if not CSV_PATH.exists():
        print(f"  [warn] CSV not found at {CSV_PATH} — category/phase will use tag fallback only")
        return lookup
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            csv_id = row.get("Test ID", "").strip()
            phase  = row.get("Phase", "").strip()
            cat    = row.get("Category", "").strip()
            if csv_id and phase and cat:
                lookup[csv_id] = (phase, cat)
    print(f"  Loaded {len(lookup)} CSV entries for category mapping")
    return lookup


def parse_md(path: Path) -> tuple[str, dict]:
    raw = path.read_text()
    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError(f"{path}: no YAML frontmatter found")
    meta = yaml.safe_load(match.group(1))
    meta["body"] = raw[match.end():].strip()
    return raw, meta


def _resolve_category(meta: dict, csv_lookup: dict) -> tuple[str | None, str | None]:
    """Return (phase, category) for a definition, using CSV lookup then tag fallback."""
    csv_ids = meta.get("csv_ids") or []
    if isinstance(csv_ids, str):
        csv_ids = [csv_ids]
    for cid in csv_ids:
        if cid in csv_lookup:
            return csv_lookup[cid]
    # Fallback: derive phase from phaseN tags
    tags = meta.get("tags") or []
    for tag in tags:
        if tag.lower() in _PHASE_TAG_NAMES:
            return _PHASE_TAG_NAMES[tag.lower()], None
    return None, None


async def seed():
    csv_lookup = _load_csv_lookup()
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        files = sorted(DEFS_DIR.glob("*.md"))
        print(f"Seeding {len(files)} definition(s)...")

        for f in files:
            raw, meta = parse_md(f)
            slug      = meta["id"]
            name      = meta["name"]
            version   = int(meta.get("version", 1))
            tags      = meta.get("tags", [])
            component = meta.get("component")
            priority  = meta.get("priority", "medium")
            timeout   = int(meta.get("timeout_seconds", 120))
            release   = meta.get("release_introduced")
            min_node_major_version = int(meta.get("min_node_major_version", 1))
            phase, category = _resolve_category(meta, csv_lookup)
            ai_allowed = bool(meta.get("ai_allowed", False))

            # Remove body from parsed JSON (it's a UI convenience field)
            parsed = {k: v for k, v in meta.items() if k != "body"}

            await conn.execute("""
                INSERT INTO tests.definitions
                  (id, slug, name, version, tags, component, priority,
                   timeout_seconds, release_introduced, definition_raw, definition_parsed,
                   min_node_major_version, is_active, created_by, category, phase, ai_allowed)
                VALUES
                  ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, true, 'seed', $13, $14, $15)
                ON CONFLICT (slug) DO UPDATE SET
                  name=EXCLUDED.name,
                  version=EXCLUDED.version,
                  tags=EXCLUDED.tags,
                  component=EXCLUDED.component,
                  priority=EXCLUDED.priority,
                  timeout_seconds=EXCLUDED.timeout_seconds,
                  definition_raw=EXCLUDED.definition_raw,
                  definition_parsed=EXCLUDED.definition_parsed,
                  min_node_major_version=EXCLUDED.min_node_major_version,
                  category=EXCLUDED.category,
                  phase=EXCLUDED.phase,
                  ai_allowed=EXCLUDED.ai_allowed,
                  updated_at=now()
            """,
                str(uuid.uuid4()), slug, name, version,
                tags, component, priority, timeout, release,
                raw, json.dumps(parsed), min_node_major_version,
                category, phase, ai_allowed,
            )
            print(f"  ✓ {slug}  [{phase or '—'} / {category or '—'}]{' [AI]' if ai_allowed else ''}")

        print("Seed complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
