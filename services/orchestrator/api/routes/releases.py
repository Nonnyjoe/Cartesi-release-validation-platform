"""
GET    /releases               — list node release catalog (image_tag/sdk/cli/devnet/contracts computed via JOIN)
POST   /releases               — manually add/upsert a node release
POST   /releases/sync          — pull all rollups-node releases from GitHub and upsert
GET    /releases/cli           — list CLI release catalog
POST   /releases/cli/sync      — pull CLI releases (v2.x) from CLI_GITHUB_REPO and upsert
GET    /releases/sdk           — list SDK release catalog
POST   /releases/sdk/sync      — pull SDK releases (v0.x) from CLI_GITHUB_REPO and upsert
GET    /releases/contracts      — list rollups-contracts release catalog
POST   /releases/contracts/sync — pull contracts releases from CONTRACTS_GITHUB_REPO and upsert
GET    /releases/devnet         — list devnet catalog
PATCH  /releases/{tag}/toolchain — set cli/sdk/devnet/contracts for a node release (no cascade)
DELETE /releases/{tag}         — soft-delete (is_active = false)

BCNF schema — FK chain
-----------------------
  release_catalog.cli_tag  → cli_catalog.tag
  cli_catalog.sdk_tag      → sdk_catalog.tag
  cli_catalog.devnet_tag   → devnet_catalog.tag
  devnet_catalog.contracts_tag → contracts_catalog.tag

All cross-reference lookups are derived at query time via reverse JOINs.
image_tag is computed: v2.x = 'cartesi/rollups-runtime:' || ltrim(sdk_tag, 'v')
                       v1.x = 'cartesi/rollups-node:'    || ltrim(node_tag, 'v')
"""
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

sys.path.insert(0, "/app/shared")
from sdk_resolver import resolve_all_versions, node_major_version as _major

log = logging.getLogger("orchestrator.releases")

router = APIRouter(tags=["releases"])

GH_API               = "https://api.github.com"
GH_RELEASES_URL      = f"{GH_API}/repos/cartesi/rollups-node/releases"
GH_HEADERS           = {
    "Accept":               "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
GITHUB_TOKEN               = os.environ.get("GITHUB_TOKEN", "")
CLI_GITHUB_REPO            = os.environ.get("CLI_GITHUB_REPO", "cartesi/cli")
CLI_RELEASES_URL_API       = f"{GH_API}/repos/{CLI_GITHUB_REPO}/releases"
CONTRACTS_GITHUB_REPO      = os.environ.get("CONTRACTS_GITHUB_REPO", "cartesi/rollups-contracts")
CONTRACTS_RELEASES_URL_API = f"{GH_API}/repos/{CONTRACTS_GITHUB_REPO}/releases"

_NODE_BUMP_RE = re.compile(
    r'rollups[- ]node[^0-9]*v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)', re.IGNORECASE
)
_SDK_IN_BODY_RE = re.compile(
    r'(?:@cartesi/sdk[@: ]+|cartesi/rollups-runtime:)v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)',
    re.IGNORECASE,
)
_CLI_IN_BODY_RE = re.compile(
    r'@cartesi/cli[@: ]+v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)', re.IGNORECASE
)
_DEVNET_IN_BODY_RE = re.compile(
    r'@cartesi/devnet[@: ]+v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)', re.IGNORECASE
)
_CONTRACTS_IN_BODY_RE = re.compile(
    r'(?:@cartesi/rollups-contracts|rollups-contracts)[@: ]+v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)',
    re.IGNORECASE,
)


# ─── Response / Request models ────────────────────────────────────────────────

class ReleaseEntry(BaseModel):
    tag:                str
    image_tag:          str
    sdk_version:        Optional[str] = None
    cli_version:        Optional[str] = None
    devnet_version:     Optional[str] = None
    contracts_version:  Optional[str] = None
    node_major_version: Optional[int] = None
    channel:            str
    label:              Optional[str] = None
    is_active:          bool
    added_at:           str
    published_at:       Optional[str] = None
    downloads:          Optional[int] = None
    body:               Optional[str] = None
    html_url:           Optional[str] = None
    total_runs:         int = 0
    avg_pass_rate:      Optional[float] = None


class ReleaseCreateIn(BaseModel):
    tag:         str
    cli_version: Optional[str] = None   # auto-resolved if omitted
    channel:     str = "stable"
    label:       Optional[str] = None


class CliReleaseEntry(BaseModel):
    tag:              str
    channel:          str
    label:            Optional[str] = None
    is_active:        bool
    added_at:         str
    published_at:     Optional[str] = None
    downloads:        Optional[int] = None
    body:             Optional[str] = None
    html_url:         Optional[str] = None
    node_release_tag: Optional[str] = None   # derived via reverse JOIN on release_catalog
    sdk_tag:          Optional[str] = None
    devnet_tag:       Optional[str] = None
    contracts_tag:    Optional[str] = None   # derived via devnet_catalog JOIN


class SdkReleaseEntry(BaseModel):
    tag:              str
    channel:          str
    label:            Optional[str] = None
    is_active:        bool
    added_at:         str
    published_at:     Optional[str] = None
    downloads:        Optional[int] = None
    body:             Optional[str] = None
    html_url:         Optional[str] = None
    node_release_tag: Optional[str] = None   # derived via cli → release reverse JOIN
    cli_tag:          Optional[str] = None   # derived via reverse JOIN on cli_catalog
    contracts_tag:    Optional[str] = None   # derived via cli → devnet → contracts JOIN


class ContractsReleaseEntry(BaseModel):
    tag:              str
    channel:          str
    label:            Optional[str] = None
    is_active:        bool
    added_at:         str
    published_at:     Optional[str] = None
    downloads:        Optional[int] = None
    body:             Optional[str] = None
    html_url:         Optional[str] = None
    devnet_tag:       Optional[str] = None   # derived via reverse JOIN on devnet_catalog
    cli_tag:          Optional[str] = None   # derived via devnet → cli reverse JOIN
    node_release_tag: Optional[str] = None   # derived via devnet → cli → release reverse JOIN
    sdk_tag:          Optional[str] = None   # derived via devnet → cli → sdk JOIN


class DevnetReleaseEntry(BaseModel):
    tag:              str
    contracts_tag:    Optional[str] = None
    channel:          str
    label:            Optional[str] = None
    is_active:        bool
    added_at:         str
    published_at:     Optional[str] = None
    downloads:        Optional[int] = None
    body:             Optional[str] = None
    html_url:         Optional[str] = None
    cli_tag:          Optional[str] = None   # derived via reverse JOIN on cli_catalog
    node_release_tag: Optional[str] = None   # derived via cli → release reverse JOIN


class ToolchainUpdateIn(BaseModel):
    """
    PATCH /{tag}/toolchain — set toolchain links for a node release.

    Each field targets exactly one table with no cascade:
      cli_version       → release_catalog.cli_tag          (which CLI this node ships with)
      sdk_version       → cli_catalog.sdk_tag              (which SDK that CLI uses)
      devnet_version    → cli_catalog.devnet_tag            (which devnet that CLI ships)
      contracts_version → devnet_catalog.contracts_tag      (which contracts that devnet bundles)
    """
    sdk_version:       Optional[str] = None
    cli_version:       Optional[str] = None
    devnet_version:    Optional[str] = None
    contracts_version: Optional[str] = None


class SyncResult(BaseModel):
    synced: int


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _derive_channel(tag: str) -> str:
    t = tag.lower()
    if "alpha" in t: return "alpha"
    if "beta"  in t: return "beta"
    return "stable"


def _parse_pub(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


# SQL expression that computes image_tag from the JOIN chain.
# c = cli_catalog alias, rc = release_catalog alias.
_IMAGE_TAG_EXPR = """
    CASE
        WHEN rc.node_major_version >= 2 AND c.sdk_tag IS NOT NULL
            THEN 'cartesi/rollups-runtime:' || LTRIM(c.sdk_tag, 'v')
        ELSE 'cartesi/rollups-node:' || LTRIM(rc.tag, 'v')
    END
""".strip()


def _row(r) -> dict:
    return {
        "tag":                r.tag,
        "image_tag":          r.image_tag,
        "sdk_version":        getattr(r, "sdk_version", None),
        "cli_version":        getattr(r, "cli_version", None),
        "devnet_version":     getattr(r, "devnet_version", None),
        "contracts_version":  getattr(r, "contracts_version", None),
        "node_major_version": getattr(r, "node_major_version", None),
        "channel":            r.channel,
        "label":              r.label or r.tag,
        "is_active":          r.is_active,
        "added_at":           r.added_at.isoformat(),
        "published_at":       r.published_at.isoformat() if r.published_at else None,
        "downloads":          r.downloads,
        "body":               r.body,
        "html_url":           r.html_url,
        "total_runs":         getattr(r, "total_runs", 0) or 0,
        "avg_pass_rate":      getattr(r, "avg_pass_rate", None),
    }


def _cli_row(r) -> dict:
    return {
        "tag":              r.tag,
        "channel":          r.channel,
        "label":            r.label or r.tag,
        "is_active":        r.is_active,
        "added_at":         r.added_at.isoformat(),
        "published_at":     r.published_at.isoformat() if r.published_at else None,
        "downloads":        r.downloads,
        "body":             r.body,
        "html_url":         r.html_url,
        "node_release_tag": getattr(r, "node_release_tag", None),
        "sdk_tag":          getattr(r, "sdk_tag", None),
        "devnet_tag":       getattr(r, "devnet_tag", None),
        "contracts_tag":    getattr(r, "contracts_tag", None),
    }


def _sdk_row(r) -> dict:
    return {
        "tag":              r.tag,
        "channel":          r.channel,
        "label":            r.label or r.tag,
        "is_active":        r.is_active,
        "added_at":         r.added_at.isoformat(),
        "published_at":     r.published_at.isoformat() if r.published_at else None,
        "downloads":        r.downloads,
        "body":             r.body,
        "html_url":         r.html_url,
        "node_release_tag": getattr(r, "node_release_tag", None),
        "cli_tag":          getattr(r, "cli_tag", None),
        "contracts_tag":    getattr(r, "contracts_tag", None),
    }


def _contracts_row(r) -> dict:
    return {
        "tag":              r.tag,
        "channel":          r.channel,
        "label":            r.label or r.tag,
        "is_active":        r.is_active,
        "added_at":         r.added_at.isoformat(),
        "published_at":     r.published_at.isoformat() if r.published_at else None,
        "downloads":        r.downloads,
        "body":             r.body,
        "html_url":         r.html_url,
        "devnet_tag":       getattr(r, "devnet_tag", None),
        "cli_tag":          getattr(r, "cli_tag", None),
        "node_release_tag": getattr(r, "node_release_tag", None),
        "sdk_tag":          getattr(r, "sdk_tag", None),
    }


def _devnet_row(r) -> dict:
    return {
        "tag":              r.tag,
        "contracts_tag":    getattr(r, "contracts_tag", None),
        "channel":          r.channel,
        "label":            r.label or r.tag,
        "is_active":        r.is_active,
        "added_at":         r.added_at.isoformat(),
        "published_at":     r.published_at.isoformat() if r.published_at else None,
        "downloads":        r.downloads,
        "body":             r.body,
        "html_url":         r.html_url,
        "cli_tag":          getattr(r, "cli_tag", None),
        "node_release_tag": getattr(r, "node_release_tag", None),
    }


async def _fetch_cli_repo_releases() -> list[dict]:
    headers = dict(GH_HEADERS)
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                CLI_RELEASES_URL_API, headers=headers, params={"per_page": "100"}
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"GitHub API error: {exc}") from exc


async def _fetch_contracts_releases() -> list[dict]:
    headers = dict(GH_HEADERS)
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                CONTRACTS_RELEASES_URL_API, headers=headers, params={"per_page": "100"}
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"GitHub API error: {exc}") from exc


# ─── Node release catalog ─────────────────────────────────────────────────────

@router.get("", response_model=list[ReleaseEntry])
async def list_releases(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text(f"""
        SELECT
            rc.tag,
            {_IMAGE_TAG_EXPR}                                           AS image_tag,
            LTRIM(c.sdk_tag, 'v')                                       AS sdk_version,
            LTRIM(c.tag, 'v')                                           AS cli_version,
            c.devnet_tag                                                AS devnet_version,
            d.contracts_tag                                             AS contracts_version,
            rc.node_major_version,
            rc.channel, rc.label, rc.is_active,
            rc.added_at, rc.published_at, rc.downloads, rc.body, rc.html_url,
            COUNT(r.id)                                                 AS total_runs,
            AVG(r.pass_rate) FILTER (WHERE r.pass_rate IS NOT NULL)     AS avg_pass_rate
        FROM github.release_catalog rc
        LEFT JOIN github.cli_catalog    c  ON c.tag  = rc.cli_tag
        LEFT JOIN github.devnet_catalog d  ON d.tag  = c.devnet_tag
        LEFT JOIN orchestrator.runs     r  ON r.release_tag = rc.tag AND r.status = 'completed'
        WHERE rc.is_active = true
        GROUP BY rc.tag, rc.cli_tag, c.tag, c.sdk_tag, c.devnet_tag, d.contracts_tag,
                 rc.node_major_version, rc.channel, rc.label, rc.is_active,
                 rc.added_at, rc.published_at, rc.downloads, rc.body, rc.html_url
        ORDER BY rc.added_at DESC
    """))
    return [_row(r) for r in rows.fetchall()]


# ─── CLI release catalog ──────────────────────────────────────────────────────

@router.get("/cli", response_model=list[CliReleaseEntry])
async def list_cli_releases(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT
            c.tag, c.sdk_tag, c.devnet_tag, c.channel, c.label, c.is_active,
            c.added_at, c.published_at, c.downloads, c.body, c.html_url,
            d.contracts_tag                 AS contracts_tag,
            rc.tag                          AS node_release_tag
        FROM github.cli_catalog c
        LEFT JOIN github.devnet_catalog  d  ON d.tag = c.devnet_tag
        LEFT JOIN github.release_catalog rc ON rc.cli_tag = c.tag
        WHERE c.is_active = true
        ORDER BY c.added_at DESC
    """))
    return [_cli_row(r) for r in rows.fetchall()]


@router.post("/cli/sync", response_model=SyncResult)
async def sync_cli_from_github(db: AsyncSession = Depends(get_db)):
    """Fetch CLI releases (v2.x) from CLI_GITHUB_REPO and upsert into cli_catalog + devnet_catalog."""
    releases = await _fetch_cli_repo_releases()
    synced = 0
    for rel in releases:
        tag = rel.get("tag_name", "").strip()
        if not tag:
            continue
        try:
            major = int(tag.lstrip("v").split(".")[0])
        except (ValueError, IndexError):
            continue
        if major < 2:
            continue  # SDK releases are v0.x; CLI releases are v2.x

        channel      = _derive_channel(tag)
        body         = (rel.get("body") or "")[:5000]
        html_url     = rel.get("html_url", "")
        downloads    = sum(a.get("download_count", 0) for a in rel.get("assets", []))
        published_at = _parse_pub(rel.get("published_at"))

        sdk_m        = _SDK_IN_BODY_RE.search(body)
        sdk_tag      = f"v{sdk_m.group(1)}" if sdk_m else None
        devnet_m     = _DEVNET_IN_BODY_RE.search(body)
        devnet_tag   = devnet_m.group(1) if devnet_m else None
        contracts_m  = _CONTRACTS_IN_BODY_RE.search(body)
        contracts_tag = contracts_m.group(1) if contracts_m else None

        # Ensure SDK exists
        if sdk_tag:
            await db.execute(text("""
                INSERT INTO github.sdk_catalog (tag, channel, label, added_at)
                VALUES (:tag, :channel, :tag, :now)
                ON CONFLICT (tag) DO NOTHING
            """), {"tag": sdk_tag, "channel": channel, "now": datetime.now(timezone.utc)})

        # Ensure contracts exists (leaf — no FKs)
        if contracts_tag:
            ctag = contracts_tag if contracts_tag.startswith("v") else f"v{contracts_tag}"
            await db.execute(text("""
                INSERT INTO github.contracts_catalog (tag, channel, label, added_at)
                VALUES (:tag, :channel, :tag, :now)
                ON CONFLICT (tag) DO NOTHING
            """), {"tag": ctag, "channel": channel, "now": datetime.now(timezone.utc)})

        # Ensure devnet exists and link to contracts
        if devnet_tag:
            ctag = (contracts_tag if contracts_tag.startswith("v") else f"v{contracts_tag}") \
                   if contracts_tag else None
            await db.execute(text("""
                INSERT INTO github.devnet_catalog (tag, contracts_tag, channel, label, added_at)
                VALUES (:tag, :contracts_tag, :channel, :tag, :now)
                ON CONFLICT (tag) DO UPDATE SET
                    contracts_tag = COALESCE(EXCLUDED.contracts_tag, github.devnet_catalog.contracts_tag)
            """), {"tag": devnet_tag, "contracts_tag": ctag,
                   "channel": channel, "now": datetime.now(timezone.utc)})

        await db.execute(text("""
            INSERT INTO github.cli_catalog
                (tag, sdk_tag, devnet_tag, channel, label, is_active,
                 added_at, published_at, downloads, body, html_url)
            VALUES
                (:tag, :sdk_tag, :devnet_tag, :channel, :tag, true,
                 :now, :published_at, :downloads, :body, :html_url)
            ON CONFLICT (tag) DO UPDATE SET
                channel      = EXCLUDED.channel,
                published_at = EXCLUDED.published_at,
                downloads    = EXCLUDED.downloads,
                body         = EXCLUDED.body,
                html_url     = EXCLUDED.html_url,
                sdk_tag      = COALESCE(EXCLUDED.sdk_tag,    github.cli_catalog.sdk_tag),
                devnet_tag   = COALESCE(EXCLUDED.devnet_tag, github.cli_catalog.devnet_tag)
        """), {
            "tag": tag, "channel": channel, "now": datetime.now(timezone.utc),
            "published_at": published_at, "downloads": downloads,
            "body": body, "html_url": html_url,
            "sdk_tag": sdk_tag, "devnet_tag": devnet_tag,
        })
        synced += 1

    await db.commit()
    log.info("Synced %d CLI releases from %s", synced, CLI_GITHUB_REPO)
    return {"synced": synced}


# ─── SDK release catalog ──────────────────────────────────────────────────────

@router.get("/sdk", response_model=list[SdkReleaseEntry])
async def list_sdk_releases(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT
            s.tag, s.channel, s.label, s.is_active,
            s.added_at, s.published_at, s.downloads, s.body, s.html_url,
            c.tag                          AS cli_tag,
            rc.tag                         AS node_release_tag,
            d.contracts_tag                AS contracts_tag
        FROM github.sdk_catalog s
        LEFT JOIN github.cli_catalog    c  ON c.sdk_tag    = s.tag
        LEFT JOIN github.release_catalog rc ON rc.cli_tag   = c.tag
        LEFT JOIN github.devnet_catalog  d  ON d.tag        = c.devnet_tag
        WHERE s.is_active = true
        ORDER BY s.added_at DESC
    """))
    return [_sdk_row(r) for r in rows.fetchall()]


@router.post("/sdk/sync", response_model=SyncResult)
async def sync_sdk_from_github(db: AsyncSession = Depends(get_db)):
    """Fetch SDK releases (v0.x) from CLI_GITHUB_REPO and upsert into sdk_catalog."""
    releases = await _fetch_cli_repo_releases()
    synced = 0
    for rel in releases:
        tag = rel.get("tag_name", "").strip()
        if not tag:
            continue
        try:
            major = int(tag.lstrip("v").split(".")[0])
        except (ValueError, IndexError):
            continue
        if major != 0:
            continue  # only SDK releases are v0.x

        channel      = _derive_channel(tag)
        body         = (rel.get("body") or "")[:5000]
        html_url     = rel.get("html_url", "")
        downloads    = sum(a.get("download_count", 0) for a in rel.get("assets", []))
        published_at = _parse_pub(rel.get("published_at"))

        await db.execute(text("""
            INSERT INTO github.sdk_catalog
                (tag, channel, label, is_active, added_at, published_at, downloads, body, html_url)
            VALUES
                (:tag, :channel, :tag, true, :now, :published_at, :downloads, :body, :html_url)
            ON CONFLICT (tag) DO UPDATE SET
                channel      = EXCLUDED.channel,
                published_at = EXCLUDED.published_at,
                downloads    = EXCLUDED.downloads,
                body         = EXCLUDED.body,
                html_url     = EXCLUDED.html_url
        """), {
            "tag": tag, "channel": channel, "now": datetime.now(timezone.utc),
            "published_at": published_at, "downloads": downloads,
            "body": body, "html_url": html_url,
        })
        synced += 1

    await db.commit()
    log.info("Synced %d SDK releases from %s", synced, CLI_GITHUB_REPO)
    return {"synced": synced}


# ─── Contracts release catalog ────────────────────────────────────────────────

@router.get("/contracts", response_model=list[ContractsReleaseEntry])
async def list_contracts_releases(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT
            con.tag, con.channel, con.label, con.is_active,
            con.added_at, con.published_at, con.downloads, con.body, con.html_url,
            d.tag       AS devnet_tag,
            c.tag       AS cli_tag,
            c.sdk_tag   AS sdk_tag,
            rc.tag      AS node_release_tag
        FROM github.contracts_catalog con
        LEFT JOIN github.devnet_catalog  d  ON d.contracts_tag = con.tag
        LEFT JOIN github.cli_catalog     c  ON c.devnet_tag    = d.tag
        LEFT JOIN github.release_catalog rc ON rc.cli_tag      = c.tag
        WHERE con.is_active = true
        ORDER BY con.added_at DESC
    """))
    return [_contracts_row(r) for r in rows.fetchall()]


@router.post("/contracts/sync", response_model=SyncResult)
async def sync_contracts_from_github(db: AsyncSession = Depends(get_db)):
    """Fetch rollups-contracts releases from CONTRACTS_GITHUB_REPO and upsert into contracts_catalog."""
    releases = await _fetch_contracts_releases()
    synced = 0
    for rel in releases:
        tag = rel.get("tag_name", "").strip()
        if not tag:
            continue

        channel      = _derive_channel(tag)
        body         = (rel.get("body") or "")[:5000]
        html_url     = rel.get("html_url", "")
        downloads    = sum(a.get("download_count", 0) for a in rel.get("assets", []))
        published_at = _parse_pub(rel.get("published_at"))

        await db.execute(text("""
            INSERT INTO github.contracts_catalog
                (tag, channel, label, is_active, added_at, published_at, downloads, body, html_url)
            VALUES
                (:tag, :channel, :tag, true, :now, :published_at, :downloads, :body, :html_url)
            ON CONFLICT (tag) DO UPDATE SET
                channel      = EXCLUDED.channel,
                published_at = EXCLUDED.published_at,
                downloads    = EXCLUDED.downloads,
                body         = EXCLUDED.body,
                html_url     = EXCLUDED.html_url
        """), {
            "tag": tag, "channel": channel, "now": datetime.now(timezone.utc),
            "published_at": published_at, "downloads": downloads,
            "body": body, "html_url": html_url,
        })
        synced += 1

    await db.commit()
    log.info("Synced %d contracts releases from %s", synced, CONTRACTS_GITHUB_REPO)
    return {"synced": synced}


# ─── Devnet catalog ───────────────────────────────────────────────────────────

@router.get("/devnet", response_model=list[DevnetReleaseEntry])
async def list_devnet_releases(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT
            d.tag, d.contracts_tag, d.channel, d.label, d.is_active,
            d.added_at, d.published_at, d.downloads, d.body, d.html_url,
            c.tag   AS cli_tag,
            rc.tag  AS node_release_tag
        FROM github.devnet_catalog d
        LEFT JOIN github.cli_catalog     c  ON c.devnet_tag = d.tag
        LEFT JOIN github.release_catalog rc ON rc.cli_tag   = c.tag
        WHERE d.is_active = true
        ORDER BY d.added_at DESC
    """))
    return [_devnet_row(r) for r in rows.fetchall()]


# ─── Node release sync ────────────────────────────────────────────────────────

@router.post("/sync", response_model=SyncResult)
async def sync_from_github(db: AsyncSession = Depends(get_db)):
    """
    Fetch all rollups-node releases from GitHub, resolve the full version chain
    via resolve_all_versions(), and upsert into release_catalog + supporting catalogs.
    """
    headers = dict(GH_HEADERS)
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(GH_RELEASES_URL, headers=headers,
                                    params={"per_page": "100"})
            resp.raise_for_status()
            releases = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"GitHub API error: {exc}") from exc

    synced = 0
    for rel in releases:
        tag = rel.get("tag_name", "").strip()
        if not tag:
            continue

        channel      = _derive_channel(tag)
        major        = _major(tag)
        downloads    = sum(a.get("download_count", 0) for a in rel.get("assets", []))
        published_at = _parse_pub(rel.get("published_at"))
        body         = (rel.get("body") or "")[:5000]
        html_url     = rel.get("html_url", "")

        cli_tag           = None
        sdk_tag           = None
        devnet_tag        = None
        contracts_version = None

        if major >= 2:
            sdk_version, cli_version, devnet_version, contracts_version = \
                await resolve_all_versions(tag, GITHUB_TOKEN)

            cli_tag    = f"v{cli_version}"    if cli_version    else None
            sdk_tag    = f"v{sdk_version}"    if sdk_version    else None
            devnet_tag = devnet_version        if devnet_version else None

            # Ensure leaf nodes exist before writing FKs
            if sdk_tag:
                await db.execute(text("""
                    INSERT INTO github.sdk_catalog (tag, channel, label, added_at)
                    VALUES (:tag, :chan, :tag, :now)
                    ON CONFLICT (tag) DO NOTHING
                """), {"tag": sdk_tag, "chan": channel, "now": datetime.now(timezone.utc)})

            if contracts_version:
                ctag = contracts_version if contracts_version.startswith("v") else f"v{contracts_version}"
                await db.execute(text("""
                    INSERT INTO github.contracts_catalog (tag, channel, label, added_at)
                    VALUES (:tag, :chan, :tag, :now)
                    ON CONFLICT (tag) DO NOTHING
                """), {"tag": ctag, "chan": channel, "now": datetime.now(timezone.utc)})
            else:
                ctag = None

            if devnet_tag:
                await db.execute(text("""
                    INSERT INTO github.devnet_catalog (tag, contracts_tag, channel, label, added_at)
                    VALUES (:tag, :contracts_tag, :chan, :tag, :now)
                    ON CONFLICT (tag) DO UPDATE SET
                        contracts_tag = COALESCE(EXCLUDED.contracts_tag, github.devnet_catalog.contracts_tag)
                """), {"tag": devnet_tag, "contracts_tag": ctag,
                       "chan": channel, "now": datetime.now(timezone.utc)})

            if cli_tag:
                await db.execute(text("""
                    INSERT INTO github.cli_catalog
                        (tag, sdk_tag, devnet_tag, channel, label, is_active, added_at)
                    VALUES (:tag, :sdk_tag, :devnet_tag, :chan, :tag, true, :now)
                    ON CONFLICT (tag) DO UPDATE SET
                        sdk_tag    = COALESCE(EXCLUDED.sdk_tag,    github.cli_catalog.sdk_tag),
                        devnet_tag = COALESCE(EXCLUDED.devnet_tag, github.cli_catalog.devnet_tag)
                """), {"tag": cli_tag, "sdk_tag": sdk_tag, "devnet_tag": devnet_tag,
                       "chan": channel, "now": datetime.now(timezone.utc)})

        await db.execute(text("""
            INSERT INTO github.release_catalog
                (tag, cli_tag, node_major_version, channel, label, is_active,
                 added_at, published_at, downloads, body, html_url)
            VALUES
                (:tag, :cli_tag, :major, :channel, :label, true,
                 :now, :published_at, :downloads, :body, :html_url)
            ON CONFLICT (tag) DO UPDATE SET
                cli_tag            = COALESCE(EXCLUDED.cli_tag, github.release_catalog.cli_tag),
                node_major_version = EXCLUDED.node_major_version,
                channel            = EXCLUDED.channel,
                published_at       = EXCLUDED.published_at,
                downloads          = EXCLUDED.downloads,
                body               = EXCLUDED.body,
                html_url           = EXCLUDED.html_url
        """), {
            "tag": tag, "cli_tag": cli_tag, "major": major,
            "channel": channel, "label": tag,
            "now": datetime.now(timezone.utc),
            "published_at": published_at, "downloads": downloads,
            "body": body, "html_url": html_url,
        })
        synced += 1

    await db.commit()
    log.info("Synced %d releases from GitHub", synced)
    return {"synced": synced}


# ─── Toolchain manual override ────────────────────────────────────────────────

@router.patch("/{tag}/toolchain", response_model=ReleaseEntry)
async def update_toolchain(tag: str, payload: ToolchainUpdateIn,
                           db: AsyncSession = Depends(get_db)):
    """
    Set toolchain links for a node release.  Each field targets exactly one
    table with no cascade — the normalized chain eliminates the need for it.

      cli_version       → release_catalog.cli_tag
      sdk_version       → cli_catalog.sdk_tag      (for that CLI)
      devnet_version    → cli_catalog.devnet_tag    (for that CLI)
      contracts_version → devnet_catalog.contracts_tag (for that devnet)
    """
    # Read current state through the JOIN chain
    row = (await db.execute(text("""
        SELECT
            rc.tag,
            rc.cli_tag,
            c.sdk_tag,
            c.devnet_tag,
            d.contracts_tag
        FROM github.release_catalog rc
        LEFT JOIN github.cli_catalog    c ON c.tag = rc.cli_tag
        LEFT JOIN github.devnet_catalog d ON d.tag = c.devnet_tag
        WHERE rc.tag = :tag
    """), {"tag": tag})).fetchone()
    if not row:
        raise HTTPException(404, f"Release {tag!r} not found")

    def _vtag(v: Optional[str], prefix: bool = True) -> Optional[str]:
        """Normalise: strip 'v', optionally re-add it."""
        if not v:
            return None
        stripped = v.lstrip("v")
        return ("v" + stripped) if prefix else stripped

    new_cli_tag        = _vtag(payload.cli_version)     if payload.cli_version     is not None else row.cli_tag
    new_sdk_tag        = _vtag(payload.sdk_version)     if payload.sdk_version     is not None else row.sdk_tag
    new_devnet_tag     = _vtag(payload.devnet_version, prefix=False) \
                         if payload.devnet_version is not None else row.devnet_tag
    new_contracts_tag  = _vtag(payload.contracts_version) \
                         if payload.contracts_version is not None else row.contracts_tag

    now = datetime.now(timezone.utc)

    # ── 1. Ensure new leaf nodes exist before writing FKs ─────────────────────
    if new_sdk_tag:
        await db.execute(text("""
            INSERT INTO github.sdk_catalog (tag, channel, label, added_at)
            VALUES (:tag, :chan, :tag, :now)
            ON CONFLICT (tag) DO NOTHING
        """), {"tag": new_sdk_tag, "chan": _derive_channel(new_sdk_tag), "now": now})

    if new_contracts_tag:
        await db.execute(text("""
            INSERT INTO github.contracts_catalog (tag, channel, label, added_at)
            VALUES (:tag, :chan, :tag, :now)
            ON CONFLICT (tag) DO NOTHING
        """), {"tag": new_contracts_tag, "chan": _derive_channel(new_contracts_tag), "now": now})

    if new_devnet_tag:
        await db.execute(text("""
            INSERT INTO github.devnet_catalog (tag, contracts_tag, channel, label, added_at)
            VALUES (:tag, :contracts_tag, :chan, :tag, :now)
            ON CONFLICT (tag) DO UPDATE SET
                contracts_tag = COALESCE(EXCLUDED.contracts_tag, github.devnet_catalog.contracts_tag)
        """), {"tag": new_devnet_tag, "contracts_tag": new_contracts_tag,
               "chan": _derive_channel(new_devnet_tag), "now": now})

    if new_cli_tag:
        await db.execute(text("""
            INSERT INTO github.cli_catalog (tag, sdk_tag, devnet_tag, channel, label, added_at)
            VALUES (:tag, :sdk_tag, :devnet_tag, :chan, :tag, :now)
            ON CONFLICT (tag) DO UPDATE SET
                sdk_tag    = COALESCE(EXCLUDED.sdk_tag,    github.cli_catalog.sdk_tag),
                devnet_tag = COALESCE(EXCLUDED.devnet_tag, github.cli_catalog.devnet_tag)
        """), {"tag": new_cli_tag, "sdk_tag": new_sdk_tag, "devnet_tag": new_devnet_tag,
               "chan": _derive_channel(new_cli_tag), "now": now})

    # ── 2. Update each table — exactly one row per table, no cascade ──────────

    # release_catalog: update cli_tag pointer
    await db.execute(text("""
        UPDATE github.release_catalog SET cli_tag = :cli_tag WHERE tag = :tag
    """), {"cli_tag": new_cli_tag, "tag": tag})

    # cli_catalog: update sdk and devnet pointers (for the CLI this node uses)
    if new_cli_tag:
        await db.execute(text("""
            UPDATE github.cli_catalog
            SET sdk_tag    = COALESCE(:sdk_tag,    sdk_tag),
                devnet_tag = COALESCE(:devnet_tag, devnet_tag)
            WHERE tag = :cli_tag
        """), {"sdk_tag": new_sdk_tag, "devnet_tag": new_devnet_tag, "cli_tag": new_cli_tag})

    # devnet_catalog: update contracts pointer (for the devnet that CLI ships)
    if new_devnet_tag and new_contracts_tag:
        await db.execute(text("""
            UPDATE github.devnet_catalog
            SET contracts_tag = :contracts_tag
            WHERE tag = :devnet_tag
        """), {"contracts_tag": new_contracts_tag, "devnet_tag": new_devnet_tag})

    await db.commit()

    # Re-read through the JOIN chain for the authoritative response
    result = (await db.execute(text(f"""
        SELECT
            rc.tag,
            {_IMAGE_TAG_EXPR}                                           AS image_tag,
            LTRIM(c.sdk_tag, 'v')                                       AS sdk_version,
            LTRIM(c.tag, 'v')                                           AS cli_version,
            c.devnet_tag                                                AS devnet_version,
            d.contracts_tag                                             AS contracts_version,
            rc.node_major_version,
            rc.channel, rc.label, rc.is_active,
            rc.added_at, rc.published_at, rc.downloads, rc.body, rc.html_url,
            0                                                           AS total_runs,
            NULL::FLOAT                                                 AS avg_pass_rate
        FROM github.release_catalog rc
        LEFT JOIN github.cli_catalog    c ON c.tag = rc.cli_tag
        LEFT JOIN github.devnet_catalog d ON d.tag = c.devnet_tag
        WHERE rc.tag = :tag
    """), {"tag": tag})).fetchone()
    return _row(result)


# ─── Manual add / soft-delete ─────────────────────────────────────────────────

@router.post("", response_model=ReleaseEntry, status_code=201)
async def add_release(body: ReleaseCreateIn, db: AsyncSession = Depends(get_db)):
    tag = body.tag.strip()
    if not tag:
        raise HTTPException(422, "tag is required")

    major   = _major(tag)
    channel = body.channel or _derive_channel(tag)
    label   = body.label or tag

    cli_tag    = None
    sdk_tag    = None
    devnet_tag = None
    contracts_tag = None

    if major >= 2:
        cli_version_raw = body.cli_version
        if not cli_version_raw:
            sdk_v, cli_v, devnet_v, contracts_v = await resolve_all_versions(tag, GITHUB_TOKEN)
            cli_tag       = f"v{cli_v}"    if cli_v        else None
            sdk_tag       = f"v{sdk_v}"    if sdk_v        else None
            devnet_tag    = devnet_v        if devnet_v     else None
            contracts_tag = f"v{contracts_v}" if contracts_v else None
        else:
            cli_tag = f"v{cli_version_raw.lstrip('v')}"

        now = datetime.now(timezone.utc)
        if sdk_tag:
            await db.execute(text("""
                INSERT INTO github.sdk_catalog (tag, channel, label, added_at)
                VALUES (:tag, :chan, :tag, :now) ON CONFLICT (tag) DO NOTHING
            """), {"tag": sdk_tag, "chan": channel, "now": now})
        if contracts_tag:
            await db.execute(text("""
                INSERT INTO github.contracts_catalog (tag, channel, label, added_at)
                VALUES (:tag, :chan, :tag, :now) ON CONFLICT (tag) DO NOTHING
            """), {"tag": contracts_tag, "chan": channel, "now": now})
        if devnet_tag:
            await db.execute(text("""
                INSERT INTO github.devnet_catalog (tag, contracts_tag, channel, label, added_at)
                VALUES (:tag, :contracts_tag, :chan, :tag, :now)
                ON CONFLICT (tag) DO UPDATE SET
                    contracts_tag = COALESCE(EXCLUDED.contracts_tag, github.devnet_catalog.contracts_tag)
            """), {"tag": devnet_tag, "contracts_tag": contracts_tag,
                   "chan": channel, "now": now})
        if cli_tag:
            await db.execute(text("""
                INSERT INTO github.cli_catalog (tag, sdk_tag, devnet_tag, channel, label, added_at)
                VALUES (:tag, :sdk_tag, :devnet_tag, :chan, :tag, :now)
                ON CONFLICT (tag) DO UPDATE SET
                    sdk_tag    = COALESCE(EXCLUDED.sdk_tag,    github.cli_catalog.sdk_tag),
                    devnet_tag = COALESCE(EXCLUDED.devnet_tag, github.cli_catalog.devnet_tag)
            """), {"tag": cli_tag, "sdk_tag": sdk_tag, "devnet_tag": devnet_tag,
                   "chan": channel, "now": now})

    await db.execute(text("""
        INSERT INTO github.release_catalog
            (tag, cli_tag, node_major_version, channel, label, is_active, added_at)
        VALUES (:tag, :cli_tag, :major, :channel, :label, true, :now)
        ON CONFLICT (tag) DO UPDATE SET
            cli_tag            = COALESCE(EXCLUDED.cli_tag, github.release_catalog.cli_tag),
            node_major_version = EXCLUDED.node_major_version,
            channel            = EXCLUDED.channel,
            label              = EXCLUDED.label,
            is_active          = true
    """), {
        "tag": tag, "cli_tag": cli_tag, "major": major,
        "channel": channel, "label": label, "now": datetime.now(timezone.utc),
    })
    await db.commit()

    row = (await db.execute(text(f"""
        SELECT
            rc.tag,
            {_IMAGE_TAG_EXPR}                                       AS image_tag,
            LTRIM(c.sdk_tag, 'v')                                   AS sdk_version,
            LTRIM(c.tag, 'v')                                       AS cli_version,
            c.devnet_tag                                            AS devnet_version,
            d.contracts_tag                                         AS contracts_version,
            rc.node_major_version,
            rc.channel, rc.label, rc.is_active,
            rc.added_at, rc.published_at, rc.downloads, rc.body, rc.html_url,
            0           AS total_runs,
            NULL::FLOAT AS avg_pass_rate
        FROM github.release_catalog rc
        LEFT JOIN github.cli_catalog    c ON c.tag = rc.cli_tag
        LEFT JOIN github.devnet_catalog d ON d.tag = c.devnet_tag
        WHERE rc.tag = :tag
    """), {"tag": tag})).fetchone()
    return _row(row)


@router.delete("/{tag:path}", status_code=204)
async def remove_release(tag: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("UPDATE github.release_catalog SET is_active = false WHERE tag = :tag RETURNING tag"),
        {"tag": tag},
    )
    if not result.fetchone():
        raise HTTPException(404, f"Release {tag!r} not found")
    await db.commit()
