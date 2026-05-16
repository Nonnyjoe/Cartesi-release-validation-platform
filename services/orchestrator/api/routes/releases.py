"""
GET    /releases               — list node release catalog with run stats
POST   /releases               — manually add/upsert a node release
POST   /releases/sync          — pull all rollups-node releases from GitHub and upsert
GET    /releases/cli           — list CLI release catalog
POST   /releases/cli/sync      — pull CLI releases (v2.x) from CLI_GITHUB_REPO and upsert
GET    /releases/sdk           — list SDK release catalog
POST   /releases/sdk/sync      — pull SDK releases (v0.x) from CLI_GITHUB_REPO and upsert
GET    /releases/contracts      — list rollups-contracts release catalog
POST   /releases/contracts/sync — pull contracts releases from CONTRACTS_GITHUB_REPO and upsert
PATCH  /releases/{tag}/toolchain — manually set sdk/cli/devnet/contracts versions
DELETE /releases/{tag}         — soft-delete (is_active = false)

SDK version resolution pipeline
--------------------------------
For v2.x releases the sync endpoint resolves the @cartesi/sdk version by:
  1. Checking a static known-mapping table (fast, no API call).
  2. Falling back to scanning the GitHub cartesi/cli releases for a body
     that mentions the rollups-node version, then extracting the SDK version
     string from that body.

The CLI repo (CLI_GITHUB_REPO, default cartesi/cli) publishes two kinds of releases:
  v2.x.x-alpha  →  @cartesi/cli releases  →  github.cli_catalog
  v0.x.x-alpha  →  @cartesi/sdk releases  →  github.sdk_catalog

Version chain:
  rollups-node → @cartesi/cli → @cartesi/devnet → rollups-contracts
  rollups-node → @cartesi/sdk (Docker image tag)
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

# shared/ is on sys.path inside the service container
sys.path.insert(0, "/app/shared")
from sdk_resolver import resolve_all_versions, derive_image_tag, node_major_version as _major

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

# Patterns for parsing release body cross-references
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
    devnet_version:     Optional[str] = None   # @cartesi/devnet version
    contracts_version:  Optional[str] = None   # rollups-contracts version
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
    image_tag:   Optional[str] = None   # auto-derived if omitted
    sdk_version: Optional[str] = None   # auto-resolved if omitted
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
    node_release_tag: Optional[str] = None
    sdk_tag:          Optional[str] = None
    devnet_tag:       Optional[str] = None   # @cartesi/devnet version this CLI ships
    contracts_tag:    Optional[str] = None   # contracts version (via devnet)


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
    node_release_tag: Optional[str] = None
    cli_tag:          Optional[str] = None
    contracts_tag:    Optional[str] = None   # derived via cli_catalog join


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
    devnet_tag:       Optional[str] = None   # @cartesi/devnet version that bundles these contracts
    cli_tag:          Optional[str] = None   # CLI release that uses this devnet
    node_release_tag: Optional[str] = None   # rollups-node release
    sdk_tag:          Optional[str] = None   # SDK release


class ToolchainUpdateIn(BaseModel):
    sdk_version:       Optional[str] = None   # accepts with or without leading 'v'
    cli_version:       Optional[str] = None   # accepts with or without leading 'v'
    devnet_version:    Optional[str] = None   # @cartesi/devnet version
    contracts_version: Optional[str] = None   # rollups-contracts version


class SyncResult(BaseModel):
    synced: int


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _derive_channel(tag: str) -> str:
    t = tag.lower()
    if "alpha" in t:
        return "alpha"
    if "beta" in t:
        return "beta"
    return "stable"


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
        "node_release_tag": r.node_release_tag,
        "sdk_tag":          r.sdk_tag,
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
        "node_release_tag": r.node_release_tag,
        "cli_tag":          r.cli_tag,
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
        "devnet_tag":       r.devnet_tag,
        "cli_tag":          r.cli_tag,
        "node_release_tag": r.node_release_tag,
        "sdk_tag":          r.sdk_tag,
    }


async def _fetch_cli_repo_releases() -> list[dict]:
    """Fetch all releases from the CLI GitHub repository (CLI_GITHUB_REPO)."""
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
    """Fetch all releases from CONTRACTS_GITHUB_REPO."""
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


def _parse_pub(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


# ─── Node release catalog ─────────────────────────────────────────────────────

@router.get("", response_model=list[ReleaseEntry])
async def list_releases(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT
            rc.tag, rc.image_tag, rc.sdk_version, rc.cli_version,
            rc.devnet_version, rc.contracts_version, rc.node_major_version,
            rc.channel, rc.label, rc.is_active,
            rc.added_at, rc.published_at, rc.downloads, rc.body, rc.html_url,
            COUNT(r.id)                                              AS total_runs,
            AVG(r.pass_rate) FILTER (WHERE r.pass_rate IS NOT NULL) AS avg_pass_rate
        FROM github.release_catalog rc
        LEFT JOIN orchestrator.runs r
               ON r.release_tag = rc.tag AND r.status = 'completed'
        WHERE rc.is_active = true
        GROUP BY rc.tag, rc.image_tag, rc.sdk_version, rc.cli_version,
                 rc.devnet_version, rc.contracts_version, rc.node_major_version,
                 rc.channel, rc.label, rc.is_active,
                 rc.added_at, rc.published_at, rc.downloads, rc.body, rc.html_url
        ORDER BY rc.added_at DESC
    """))
    return [_row(r) for r in rows.fetchall()]


# ─── CLI release catalog ──────────────────────────────────────────────────────

@router.get("/cli", response_model=list[CliReleaseEntry])
async def list_cli_releases(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT tag, channel, label, is_active, added_at, published_at, downloads,
               body, html_url, node_release_tag, sdk_tag, devnet_tag, contracts_tag
        FROM github.cli_catalog
        WHERE is_active = true
        ORDER BY added_at DESC
    """))
    return [_cli_row(r) for r in rows.fetchall()]


@router.post("/cli/sync", response_model=SyncResult)
async def sync_cli_from_github(db: AsyncSession = Depends(get_db)):
    """Fetch CLI releases (v2.x) from CLI_GITHUB_REPO and upsert into cli_catalog."""
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
            continue  # skip SDK releases (v0.x); CLI releases are v2.x

        channel      = _derive_channel(tag)
        body         = (rel.get("body") or "")[:5000]
        html_url     = rel.get("html_url", "")
        downloads    = sum(a.get("download_count", 0) for a in rel.get("assets", []))
        published_at = _parse_pub(rel.get("published_at"))

        node_m           = _NODE_BUMP_RE.search(body)
        node_release_tag = f"v{node_m.group(1)}" if node_m else None
        sdk_m            = _SDK_IN_BODY_RE.search(body)
        sdk_tag          = f"v{sdk_m.group(1)}" if sdk_m else None
        devnet_m         = _DEVNET_IN_BODY_RE.search(body)
        devnet_tag       = devnet_m.group(1) if devnet_m else None
        contracts_m      = _CONTRACTS_IN_BODY_RE.search(body)
        contracts_tag    = contracts_m.group(1) if contracts_m else None

        await db.execute(text("""
            INSERT INTO github.cli_catalog
                (tag, channel, label, is_active, added_at, published_at, downloads,
                 body, html_url, node_release_tag, sdk_tag, devnet_tag, contracts_tag)
            VALUES
                (:tag, :channel, :tag, true, :now, :published_at, :downloads,
                 :body, :html_url, :node_release_tag, :sdk_tag, :devnet_tag, :contracts_tag)
            ON CONFLICT (tag) DO UPDATE SET
                channel          = EXCLUDED.channel,
                published_at     = EXCLUDED.published_at,
                downloads        = EXCLUDED.downloads,
                body             = EXCLUDED.body,
                html_url         = EXCLUDED.html_url,
                node_release_tag = COALESCE(EXCLUDED.node_release_tag,
                                            github.cli_catalog.node_release_tag),
                sdk_tag          = COALESCE(EXCLUDED.sdk_tag,
                                            github.cli_catalog.sdk_tag),
                devnet_tag       = COALESCE(EXCLUDED.devnet_tag,
                                            github.cli_catalog.devnet_tag),
                contracts_tag    = COALESCE(EXCLUDED.contracts_tag,
                                            github.cli_catalog.contracts_tag)
        """), {
            "tag": tag, "channel": channel, "now": datetime.now(timezone.utc),
            "published_at": published_at, "downloads": downloads,
            "body": body, "html_url": html_url,
            "node_release_tag": node_release_tag, "sdk_tag": sdk_tag,
            "devnet_tag": devnet_tag, "contracts_tag": contracts_tag,
        })
        synced += 1

    await db.commit()
    log.info("Synced %d CLI releases from %s", synced, CLI_GITHUB_REPO)
    return {"synced": synced}


# ─── SDK release catalog ──────────────────────────────────────────────────────

@router.get("/sdk", response_model=list[SdkReleaseEntry])
async def list_sdk_releases(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT s.tag, s.channel, s.label, s.is_active, s.added_at, s.published_at,
               s.downloads, s.body, s.html_url, s.node_release_tag, s.cli_tag,
               c.contracts_tag
        FROM github.sdk_catalog s
        LEFT JOIN github.cli_catalog c ON c.tag = s.cli_tag
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

        node_m           = _NODE_BUMP_RE.search(body)
        node_release_tag = f"v{node_m.group(1)}" if node_m else None
        cli_m            = _CLI_IN_BODY_RE.search(body)
        cli_tag          = f"v{cli_m.group(1)}" if cli_m else None

        await db.execute(text("""
            INSERT INTO github.sdk_catalog
                (tag, channel, label, is_active, added_at, published_at, downloads,
                 body, html_url, node_release_tag, cli_tag)
            VALUES
                (:tag, :channel, :tag, true, :now, :published_at, :downloads,
                 :body, :html_url, :node_release_tag, :cli_tag)
            ON CONFLICT (tag) DO UPDATE SET
                channel          = EXCLUDED.channel,
                published_at     = EXCLUDED.published_at,
                downloads        = EXCLUDED.downloads,
                body             = EXCLUDED.body,
                html_url         = EXCLUDED.html_url,
                node_release_tag = COALESCE(EXCLUDED.node_release_tag,
                                            github.sdk_catalog.node_release_tag),
                cli_tag          = COALESCE(EXCLUDED.cli_tag,
                                            github.sdk_catalog.cli_tag)
        """), {
            "tag": tag, "channel": channel, "now": datetime.now(timezone.utc),
            "published_at": published_at, "downloads": downloads,
            "body": body, "html_url": html_url,
            "node_release_tag": node_release_tag, "cli_tag": cli_tag,
        })
        synced += 1

    await db.commit()
    log.info("Synced %d SDK releases from %s", synced, CLI_GITHUB_REPO)
    return {"synced": synced}


# ─── Contracts release catalog ────────────────────────────────────────────────

@router.get("/contracts", response_model=list[ContractsReleaseEntry])
async def list_contracts_releases(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT tag, channel, label, is_active, added_at, published_at, downloads,
               body, html_url, devnet_tag, cli_tag, node_release_tag, sdk_tag
        FROM github.contracts_catalog
        WHERE is_active = true
        ORDER BY added_at DESC
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
                (tag, channel, label, is_active, added_at, published_at, downloads,
                 body, html_url)
            VALUES
                (:tag, :channel, :tag, true, :now, :published_at, :downloads,
                 :body, :html_url)
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


# ─── Node release sync ────────────────────────────────────────────────────────

@router.post("/sync", response_model=SyncResult)
async def sync_from_github(db: AsyncSession = Depends(get_db)):
    """
    Fetch all rollups-node releases from the GitHub API and upsert into release_catalog.
    For each v2.x release, all four toolchain versions (SDK, CLI, devnet, contracts)
    are resolved by scanning the cartesi/cli releases.
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

        sdk_version       = None
        cli_version       = None
        devnet_version    = None
        contracts_version = None
        if major >= 2:
            sdk_version, cli_version, devnet_version, contracts_version = \
                await resolve_all_versions(tag, GITHUB_TOKEN)

        image_tag = derive_image_tag(tag, sdk_version)

        await db.execute(text("""
            INSERT INTO github.release_catalog
                (tag, image_tag, sdk_version, cli_version, devnet_version, contracts_version,
                 node_major_version, channel, label, is_active, added_at,
                 published_at, downloads, body, html_url)
            VALUES
                (:tag, :image_tag, :sdk_version, :cli_version, :devnet, :contracts,
                 :node_major_version, :channel, :label, true, :now,
                 :published_at, :downloads, :body, :html_url)
            ON CONFLICT (tag) DO UPDATE SET
                image_tag          = EXCLUDED.image_tag,
                sdk_version        = EXCLUDED.sdk_version,
                cli_version        = EXCLUDED.cli_version,
                devnet_version     = COALESCE(EXCLUDED.devnet_version,
                                              github.release_catalog.devnet_version),
                contracts_version  = COALESCE(EXCLUDED.contracts_version,
                                              github.release_catalog.contracts_version),
                node_major_version = EXCLUDED.node_major_version,
                channel            = EXCLUDED.channel,
                published_at       = EXCLUDED.published_at,
                downloads          = EXCLUDED.downloads,
                body               = EXCLUDED.body,
                html_url           = EXCLUDED.html_url
        """), {
            "tag":                tag,
            "image_tag":          image_tag,
            "sdk_version":        sdk_version,
            "cli_version":        cli_version,
            "devnet":             devnet_version,
            "contracts":          contracts_version,
            "node_major_version": major,
            "channel":            channel,
            "label":              tag,
            "now":                datetime.now(timezone.utc),
            "published_at":       published_at,
            "downloads":          downloads,
            "body":               body,
            "html_url":           html_url,
        })
        synced += 1

    await db.commit()
    log.info("Synced %d releases from GitHub (with SDK/CLI/devnet/contracts resolution)", synced)
    return {"synced": synced}


# ─── Toolchain manual override ────────────────────────────────────────────────

@router.patch("/{tag}/toolchain", response_model=ReleaseEntry)
async def update_toolchain(tag: str, payload: ToolchainUpdateIn,
                           db: AsyncSession = Depends(get_db)):
    """Manually set sdk/cli/devnet/contracts versions for a node release and cascade cross-refs."""
    row = (await db.execute(
        text("""
            SELECT tag, sdk_version, cli_version, devnet_version, contracts_version
            FROM github.release_catalog WHERE tag = :tag
        """),
        {"tag": tag},
    )).fetchone()
    if not row:
        raise HTTPException(404, f"Release {tag!r} not found")

    def _clean(v: Optional[str]) -> Optional[str]:
        """Strip leading 'v' so storage is consistent (e.g. '0.12.0-alpha.39')."""
        return v.lstrip("v") if v else v

    sdk_version       = _clean(payload.sdk_version)       if payload.sdk_version       is not None else row.sdk_version
    cli_version       = _clean(payload.cli_version)       if payload.cli_version       is not None else row.cli_version
    devnet_version    = _clean(payload.devnet_version)    if payload.devnet_version    is not None else row.devnet_version
    contracts_version = _clean(payload.contracts_version) if payload.contracts_version is not None else row.contracts_version
    image_tag         = derive_image_tag(tag, sdk_version)

    await db.execute(text("""
        UPDATE github.release_catalog
        SET sdk_version = :sdk, cli_version = :cli,
            devnet_version = :devnet, contracts_version = :contracts,
            image_tag = :img
        WHERE tag = :tag
    """), {
        "tag":       tag,
        "sdk":       sdk_version,
        "cli":       cli_version,
        "devnet":    devnet_version,
        "contracts": contracts_version,
        "img":       image_tag,
    })

    # Cascade: update cli_catalog — it is the single source of truth for the
    # version chain. All four toolchain fields are written in one statement so
    # that the sdk, devnet, and contracts cross-refs visible on the SDK and
    # Contracts release cards stay consistent with whatever the user just set.
    if cli_version:
        await db.execute(text("""
            UPDATE github.cli_catalog
            SET node_release_tag = :node,
                sdk_tag          = COALESCE(:sdk_tag,      sdk_tag),
                devnet_tag       = COALESCE(:devnet_tag,   devnet_tag),
                contracts_tag    = COALESCE(:contracts_tag, contracts_tag)
            WHERE tag = :cli
        """), {
            "node":          tag,
            "cli":           f"v{cli_version}",
            "sdk_tag":       f"v{sdk_version}"    if sdk_version       else None,
            "devnet_tag":    devnet_version                             if devnet_version    else None,
            "contracts_tag": contracts_version                         if contracts_version else None,
        })

    # Cascade: update sdk_catalog → which node release this SDK targets
    if sdk_version:
        await db.execute(text("""
            UPDATE github.sdk_catalog SET node_release_tag = :node WHERE tag = :sdk
        """), {"node": tag, "sdk": f"v{sdk_version}"})

    # Cascade: update contracts_catalog → which node release these contracts target
    if contracts_version:
        await db.execute(text("""
            UPDATE github.contracts_catalog
            SET node_release_tag = :node,
                cli_tag          = COALESCE(:cli_tag, cli_tag),
                sdk_tag          = COALESCE(:sdk_tag, sdk_tag)
            WHERE tag = :ctag
        """), {
            "node":    tag,
            "ctag":    f"v{contracts_version}",
            "cli_tag": f"v{cli_version}" if cli_version else None,
            "sdk_tag": f"v{sdk_version}" if sdk_version else None,
        })

    await db.commit()

    result = (await db.execute(text("""
        SELECT rc.*,
               COUNT(r.id)                                              AS total_runs,
               AVG(r.pass_rate) FILTER (WHERE r.pass_rate IS NOT NULL) AS avg_pass_rate
        FROM github.release_catalog rc
        LEFT JOIN orchestrator.runs r ON r.release_tag = rc.tag AND r.status = 'completed'
        WHERE rc.tag = :tag
        GROUP BY rc.tag, rc.image_tag, rc.sdk_version, rc.cli_version,
                 rc.devnet_version, rc.contracts_version, rc.node_major_version,
                 rc.channel, rc.label, rc.is_active,
                 rc.added_at, rc.published_at, rc.downloads, rc.body, rc.html_url
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

    sdk_version       = body.sdk_version
    cli_version       = body.cli_version
    devnet_version    = None
    contracts_version = None
    if major >= 2 and (not sdk_version or not cli_version):
        resolved_sdk, resolved_cli, devnet_version, contracts_version = \
            await resolve_all_versions(tag, GITHUB_TOKEN)
        sdk_version = sdk_version or resolved_sdk
        cli_version = cli_version or resolved_cli

    image_tag = body.image_tag or derive_image_tag(tag, sdk_version)

    await db.execute(text("""
        INSERT INTO github.release_catalog
            (tag, image_tag, sdk_version, cli_version, devnet_version, contracts_version,
             node_major_version, channel, label, is_active, added_at)
        VALUES
            (:tag, :image_tag, :sdk_version, :cli_version, :devnet, :contracts,
             :major, :channel, :label, true, :now)
        ON CONFLICT (tag) DO UPDATE SET
            image_tag          = EXCLUDED.image_tag,
            sdk_version        = EXCLUDED.sdk_version,
            cli_version        = EXCLUDED.cli_version,
            devnet_version     = EXCLUDED.devnet_version,
            contracts_version  = EXCLUDED.contracts_version,
            node_major_version = EXCLUDED.node_major_version,
            channel            = EXCLUDED.channel,
            label              = EXCLUDED.label,
            is_active          = true
    """), {
        "tag": tag, "image_tag": image_tag, "sdk_version": sdk_version,
        "cli_version": cli_version, "devnet": devnet_version, "contracts": contracts_version,
        "major": major, "channel": channel, "label": label,
        "now": datetime.now(timezone.utc),
    })
    await db.commit()

    row = (await db.execute(text("""
        SELECT rc.*,
               0           AS total_runs,
               NULL::FLOAT AS avg_pass_rate
        FROM github.release_catalog rc
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
