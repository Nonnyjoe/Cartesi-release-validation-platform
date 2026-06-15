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


# Slug-prefix → (phase, category) used when CSV lookup and tag fallback both miss
_SLUG_CATEGORY: list[tuple[str, str, str]] = [
    # (prefix_or_exact, phase, category) — checked with startswith in order
    ("cli-doctor-",           "Phase 1: Environment",             "CLI - doctor"),
    ("cli-create-",           "Phase 1: Environment",             "CLI - create"),
    ("cli-build-",            "Phase 1: Environment",             "CLI - build"),
    ("cli-run-",              "Phase 1: Environment",             "CLI - run"),
    ("cli-deploy-",           "Phase 1: Environment",             "CLI - deploy"),
    ("cli-deposit-",          "Phase 1: Environment",             "CLI - deposit"),
    ("cli-send-",             "Phase 1: Environment",             "CLI - send"),
    ("cli-logs-",             "Phase 1: Environment",             "CLI - logs"),
    ("cli-shell-",            "Phase 1: Environment",             "CLI - shell"),
    ("cli-status-",           "Phase 1: Environment",             "CLI - status"),
    ("cli-version-",          "Phase 1: Environment",             "CLI - version"),
    ("cli-machine-hash-",     "Phase 1: Environment",             "CLI - hash"),
    ("cli-hash-",             "Phase 1: Environment",             "CLI - hash"),
    ("cli-help-",             "Phase 1: Environment",             "CLI - help"),
    ("cli-clean-",            "Phase 1: Environment",             "CLI - clean"),
    ("cli-address-book-",     "Phase 1: Environment",             "CLI - address-book"),
    ("cli-cast-interop-",     "Phase 1: Environment",             "CLI - tooling"),
    ("restart-",              "Phase 2: Clean Restarts",          "Services"),
    ("erc1155-",              "Phase 3: Inputs (Local)",          "ERC1155"),
    ("erc20-",                "Phase 3: Inputs (Local)",          "ERC20"),
    ("erc721-",               "Phase 3: Inputs (Local)",          "ERC721"),
    ("ether-",                "Phase 3: Inputs (Local)",          "ETH"),
    ("advance-state-",        "Phase 3: Inputs (Local)",          "ETH"),
    ("generic-",              "Phase 3: Inputs (Local)",          "Generic"),
    ("cloud-erc1155-",        "Phase 4: Inputs (Remote)",         "ERC1155"),
    ("cloud-erc20-",          "Phase 4: Inputs (Remote)",         "ERC20"),
    ("cloud-erc721-",         "Phase 4: Inputs (Remote)",         "ERC721"),
    ("cloud-eth-",            "Phase 4: Inputs (Remote)",         "ETH"),
    ("cloud-ether-",          "Phase 4: Inputs (Remote)",         "ETH"),
    ("cloud-generic-",        "Phase 4: Inputs (Remote)",         "Generic"),
    ("cloud-massive-",        "Phase 4: Inputs (Remote)",         "Edge Cases"),
    ("cloud-same-block-",     "Phase 4: Inputs (Remote)",         "Edge Cases"),
    ("notice-",               "Phase 5: VM Outputs",              "Notices"),
    ("oversized-notice-",     "Phase 5: VM Outputs",              "Notices"),
    ("report-",               "Phase 5: VM Outputs",              "Reports"),
    ("voucher-generation-",   "Phase 5: VM Outputs",              "Vouchers"),
    ("delegatecall-",         "Phase 6: Voucher Execution",       "DELEGATECALL Vouchers"),
    ("e2e-",                  "Phase 7: Token Portals",           "E2E Lifecycle"),
    ("execute-voucher-",      "Phase 7: Token Portals",           "Vouchers"),
    ("mint-nft-",             "Phase 7: Token Portals",           "Mint"),
    ("overdraft-",            "Phase 7: Token Portals",           "Overdraft"),
    ("prove-validate-",       "Phase 7: Token Portals",           "Notices"),
    ("validate-notice-",      "Phase 7: Token Portals",           "Notices"),
    ("voucher-execution-",    "Phase 7: Token Portals",           "Vouchers"),
    ("voucher-",              "Phase 5: VM Outputs",              "Vouchers"),
    ("jsonrpc-",              "Phase 8: Persistence & Recovery",  "Edge Cases"),
    ("chaos-",                "Phase 9: Chaos & Fault Tolerance", "Chaos"),
    ("cloud-recovery-",       "Phase 9: Chaos & Fault Tolerance", "Recovery"),
    ("dirty-restart-",        "Phase 9: Chaos & Fault Tolerance", "Dirty Restarts"),
    ("feature-",              "Phase 9: Chaos & Fault Tolerance", "Feature Flags"),
    ("snapshot-",             "Phase 9: Chaos & Fault Tolerance", "Snapshots"),
    ("ws-",                   "Phase 9: Chaos & Fault Tolerance", "Recovery"),
    ("l1-reorg-",             "Phase 9: Chaos & Fault Tolerance", "Reorgs"),
    ("consensus-",            "Phase 10: Multi-App & Consensus",  "Consensus"),
    ("multi-app-",            "Phase 10: Multi-App & Consensus",  "Multi-App"),
    ("determinism-",          "Phase 11: Security & Limits",      "Determinism"),
    ("security-",             "Phase 11: Security & Limits",      "Security"),
    ("internal-cli-app-",     "Phase 12: Internal CLI",           "Application Mgmt"),
    ("internal-cli-db-",      "Phase 12: Internal CLI",           "Database"),
    ("internal-cli-deploy-",  "Phase 12: Internal CLI",           "Deployment"),
    ("internal-cli-read-",    "Phase 12: Internal CLI",           "Read"),
    ("internal-cli-send-",    "Phase 12: Internal CLI",           "Inputs"),
    ("internal-cli-",         "Phase 12: Internal CLI",           "Diagnostics"),
    ("health-advancer-",      "Phase 13: Telemetry & Health",     "Advancer"),
    ("health-claimer-",       "Phase 13: Telemetry & Health",     "Claimer"),
    ("health-evm-reader-",    "Phase 13: Telemetry & Health",     "EVM Reader"),
    ("health-jsonrpc-",       "Phase 13: Telemetry & Health",     "JSON-RPC API"),
    ("health-validator-",     "Phase 13: Telemetry & Health",     "Validator"),
    ("metrics-",              "Phase 13: Telemetry & Health",     "Metrics"),
    ("config-advancer-",      "Phase 14: Configuration",          "Advancer"),
    ("config-auth-",          "Phase 14: Configuration",          "Auth"),
    ("config-epoch-",         "Phase 14: Configuration",          "Epoch"),
    ("config-log-",           "Phase 14: Configuration",          "Logging"),
    ("config-ws-",            "Phase 14: Configuration",          "EVM Reader"),
    ("config-",               "Phase 14: Configuration",          "Startup"),
    ("inspect-",              "Phase 15: Inspect Service",        "Basic"),
    ("perf-",                 "Phase 17: Performance & Load",     "Latency"),
    ("performance-",          "Phase 17: Performance & Load",     "Throughput"),
]


def _resolve_category(meta: dict, csv_lookup: dict) -> tuple[str | None, str | None]:
    """Return (phase, category) for a definition, using CSV lookup → tag fallback → slug fallback."""
    # 1. CSV lookup by csv_ids
    csv_ids = meta.get("csv_ids") or []
    if isinstance(csv_ids, str):
        csv_ids = [csv_ids]
    for cid in csv_ids:
        if cid in csv_lookup:
            return csv_lookup[cid]

    # 2. Inline frontmatter fields
    if meta.get("phase") and meta.get("category"):
        return meta["phase"], meta["category"]

    # 3. Phase tag fallback (sets phase only)
    tags = meta.get("tags") or []
    for tag in tags:
        if tag.lower() in _PHASE_TAG_NAMES:
            phase = _PHASE_TAG_NAMES[tag.lower()]
            # Still try slug fallback for category within the resolved phase
            slug = meta.get("id", "")
            for prefix, _ph, cat in _SLUG_CATEGORY:
                if slug.startswith(prefix):
                    return phase, cat
            return phase, None

    # 4. Slug-prefix fallback
    slug = meta.get("id", "")
    for prefix, phase, cat in _SLUG_CATEGORY:
        if slug.startswith(prefix):
            return phase, cat

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
            # AI manual execution covers the same catalog as the Tests section,
            # except the chaos phase (needs chaos-gated tools). YAML frontmatter
            # `ai_allowed:` still overrides per test (explicit opt-in/out).
            if "ai_allowed" in meta:
                ai_allowed = bool(meta.get("ai_allowed"))
            else:
                ai_allowed = (phase or "") != "Phase 9: Chaos & Fault Tolerance"

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
