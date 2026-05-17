"""
services/github-watcher/poller.py

Polls GitHub Releases API on a fixed interval — three independent watchers:

  1. rollups-node releases  (GITHUB_REPO)
     Detects new node releases, resolves the full toolchain chain on first
     sight, inserts github.releases + github.release_catalog, publishes to
     rvp.releases so the orchestrator creates a run.

  2. CLI releases  (CLI_GITHUB_REPO, tag pattern v2.x.x)
     Detects new @cartesi/cli releases *independently* of node releases.
     When a new CLI is found it:
       a. Upserts the full chain (contracts → devnet → sdk → cli).
       b. Finds any release_catalog rows whose node version matches the
          "bump rollups-node to vX.Y.Z" mention in the CLI release body.
       c. Backfills release_catalog.cli_tag so the toolchain is now known.
       d. Publishes a release event for the affected node tag if no run has
          ever been triggered for it — allowing the orchestrator to kick off
          a properly-toolchained run even if it was first seen without one.

  3. rollups-contracts releases  (CONTRACTS_GITHUB_REPO)
     Keeps contracts_catalog fresh so devnet → contracts links are resolved.

All three run in the same asyncio loop and share one RabbitMQ connection.
"""
import asyncio
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone

import aio_pika
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text

sys.path.insert(0, "/app/shared")
from sdk_resolver import resolve_all_versions, derive_image_tag, node_major_version as _major

log = logging.getLogger("github-watcher.poller")

# ── Environment ───────────────────────────────────────────────────────────────
GITHUB_TOKEN          = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO           = os.getenv("GITHUB_REPO", "cartesi/rollups-node")
CLI_GITHUB_REPO       = os.getenv("CLI_GITHUB_REPO", "cartesi/cli")
CONTRACTS_GITHUB_REPO = os.getenv("CONTRACTS_GITHUB_REPO", "cartesi/rollups-contracts")

POLL_INTERVAL         = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
CLI_POLL_ENABLED      = os.getenv("CLI_POLL_ENABLED", "true").lower() not in ("false", "0", "no")
RABBITMQ_URL          = os.getenv("RABBITMQ_URL", "amqp://rvp:rvp_secret@rabbitmq:5672/rvp")
DATABASE_URL          = os.getenv("DATABASE_URL", "postgresql+asyncpg://rvp_github:rvp_secret@postgres:5432/rvp")

RATE_LIMIT_FLOOR      = int(os.getenv("RATE_LIMIT_FLOOR", "20"))

# ── GitHub API ────────────────────────────────────────────────────────────────
GH_API = "https://api.github.com"
HEADERS = {
    "Accept":               "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

# ── DB engine ─────────────────────────────────────────────────────────────────
engine = create_async_engine(DATABASE_URL, echo=False)

# ── Regex patterns for parsing GitHub release bodies ─────────────────────────
_NODE_BUMP_RE = re.compile(
    r'rollups[- ]node[^0-9]*v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)', re.IGNORECASE
)
_SDK_IN_BODY_RE = re.compile(
    r'(?:@cartesi/sdk[@: ]+|cartesi/rollups-runtime:|cartesi/rollups-database:)'
    r'v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)',
    re.IGNORECASE,
)
_DEVNET_IN_BODY_RE = re.compile(
    r'@cartesi/devnet[@: ]+v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)', re.IGNORECASE
)
_CONTRACTS_IN_BODY_RE = re.compile(
    r'(?:@cartesi/rollups-contracts|rollups-contracts)[@: ]+v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)',
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _check_rate_limit(response: httpx.Response) -> bool:
    remaining = int(response.headers.get("X-RateLimit-Remaining", 999))
    if remaining < RATE_LIMIT_FLOOR:
        reset_ts = response.headers.get("X-RateLimit-Reset", "unknown")
        log.warning("GitHub rate limit low: %d remaining, resets at %s", remaining, reset_ts)
        return False
    return True


def _derive_channel(tag: str) -> str:
    t = tag.lower()
    if "alpha" in t: return "alpha"
    if "beta"  in t: return "beta"
    return "stable"


def _parse_pub(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


async def _publish_release_event(channel: aio_pika.Channel, release: dict, prs: list[dict]):
    """Publish release event to rvp.releases fanout. Orchestrator creates the run."""
    exchange = await channel.get_exchange("rvp.releases")
    payload  = {
        "event_id":     str(uuid.uuid4()),
        "service":      "github-watcher",
        "ts":           datetime.now(timezone.utc).isoformat(),
        "tag_name":     release["tag_name"],
        "release_name": release.get("name", release["tag_name"]),
        "body":         (release.get("body") or "")[:2000],
        "author":       release.get("author", {}).get("login", "unknown"),
        "prs":          prs,
        "html_url":     release.get("html_url", ""),
    }
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
        ),
        routing_key="",   # fanout — routing key ignored
    )
    log.info("Published release event for %s", release["tag_name"])


# ─────────────────────────────────────────────────────────────────────────────
# Watcher 1 — rollups-node releases
# ─────────────────────────────────────────────────────────────────────────────

async def _get_latest_release(client: httpx.AsyncClient) -> dict | None:
    try:
        resp = await client.get(
            f"{GH_API}/repos/{GITHUB_REPO}/releases/latest", headers=HEADERS
        )
        if resp.status_code == 404:
            log.warning("No releases found for %s", GITHUB_REPO)
            return None
        if resp.status_code in (403, 429):
            log.warning("GitHub rate limit hit (HTTP %d). Reset at: %s",
                        resp.status_code, resp.headers.get("X-RateLimit-Reset", "unknown"))
            return None
        resp.raise_for_status()
        _check_rate_limit(resp)
        return resp.json()
    except Exception as e:
        log.error("Failed to fetch latest node release: %s", e)
        return None


async def _get_prs_for_tag(client: httpx.AsyncClient, tag: str, prev_tag: str | None) -> list[dict]:
    """Return up to 5 PR metadata dicts merged between prev_tag and tag."""
    try:
        if not prev_tag:
            return []

        compare_url = f"{GH_API}/repos/{GITHUB_REPO}/compare/{prev_tag}...{tag}"
        resp = await client.get(compare_url, headers=HEADERS)
        if resp.status_code != 200:
            return []
        if not _check_rate_limit(resp):
            return []

        pr_numbers: set[str] = set()
        for commit in resp.json().get("commits", []):
            msg = commit.get("commit", {}).get("message", "")
            pr_numbers.update(re.findall(r"#(\d+)", msg))

        prs: list[dict] = []
        for pr_num in list(pr_numbers)[:5]:
            try:
                pr_resp = await client.get(
                    f"{GH_API}/repos/{GITHUB_REPO}/pulls/{pr_num}", headers=HEADERS
                )
                if pr_resp.status_code == 200:
                    pr = pr_resp.json()
                    prs.append({
                        "number": pr.get("number"),
                        "title":  pr.get("title"),
                        "body":   (pr.get("body") or "")[:500],
                        "author": pr.get("user", {}).get("login"),
                        "labels": [lb["name"] for lb in pr.get("labels", [])],
                    })
                if not _check_rate_limit(pr_resp):
                    break
            except Exception:
                pass
        return prs
    except Exception as e:
        log.error("Failed to fetch PRs: %s", e)
        return []


async def _is_node_release_already_processed(tag: str) -> bool:
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT id FROM github.releases WHERE tag_name = :tag"),
            {"tag": tag},
        )
        return result.fetchone() is not None


async def _get_previous_tag() -> str | None:
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT tag_name FROM github.releases ORDER BY published_at DESC LIMIT 1")
        )
        row = result.fetchone()
        return row[0] if row else None


async def _insert_release(release: dict, prs: list[dict]):
    """Insert into github.releases."""
    release_id = str(uuid.uuid4())
    pr_numbers = [pr["number"] for pr in prs if pr.get("number")]
    async with AsyncSession(engine) as session:
        await session.execute(
            text("""
                INSERT INTO github.releases
                    (id, tag_name, release_name, body, html_url,
                     pr_numbers, published_at, run_triggered)
                VALUES
                    (:id, :tag, :name, :body, :html_url,
                     :pr_numbers, :pub_at, false)
                ON CONFLICT (tag_name) DO NOTHING
            """),
            {
                "id":         release_id,
                "tag":        release["tag_name"],
                "name":       release.get("name", release["tag_name"]),
                "body":       (release.get("body") or "")[:5000],
                "html_url":   release.get("html_url", ""),
                "pr_numbers": pr_numbers,
                "pub_at":     datetime.fromisoformat(
                    release["published_at"].replace("Z", "+00:00")
                ),
            },
        )
        await session.commit()


async def _upsert_node_catalog(release: dict):
    """
    Keep the normalized version chain up-to-date when a new rollups-node release
    is detected.  Writes leaf-to-root so FK constraints are satisfied:
      contracts_catalog → devnet_catalog → sdk_catalog → cli_catalog → release_catalog
    """
    tag      = release["tag_name"]
    major    = _major(tag)
    channel  = _derive_channel(tag)
    downloads = sum(a.get("download_count", 0) for a in release.get("assets", []))
    published_at = _parse_pub(release.get("published_at"))
    body     = (release.get("body") or "")[:5000]
    html_url = release.get("html_url", "")

    cli_tag       = None
    sdk_tag       = None
    devnet_tag    = None
    contracts_tag = None

    if major >= 2:
        sdk_version, cli_version, devnet_version, contracts_version = \
            await resolve_all_versions(tag, GITHUB_TOKEN)
        cli_tag       = f"v{cli_version}"       if cli_version       else None
        sdk_tag       = f"v{sdk_version}"       if sdk_version       else None
        devnet_tag    = devnet_version           if devnet_version    else None
        contracts_tag = f"v{contracts_version}" if contracts_version else None

    now = datetime.now(timezone.utc)

    async with AsyncSession(engine) as session:
        if sdk_tag:
            await session.execute(text("""
                INSERT INTO github.sdk_catalog (tag, channel, label, added_at)
                VALUES (:tag, :chan, :tag, :now) ON CONFLICT (tag) DO NOTHING
            """), {"tag": sdk_tag, "chan": channel, "now": now})

        if contracts_tag:
            await session.execute(text("""
                INSERT INTO github.contracts_catalog (tag, channel, label, added_at)
                VALUES (:tag, :chan, :tag, :now) ON CONFLICT (tag) DO NOTHING
            """), {"tag": contracts_tag, "chan": channel, "now": now})

        if devnet_tag:
            await session.execute(text("""
                INSERT INTO github.devnet_catalog
                    (tag, contracts_tag, channel, label, added_at)
                VALUES (:tag, :contracts_tag, :chan, :tag, :now)
                ON CONFLICT (tag) DO UPDATE SET
                    contracts_tag = COALESCE(EXCLUDED.contracts_tag,
                                             github.devnet_catalog.contracts_tag)
            """), {"tag": devnet_tag, "contracts_tag": contracts_tag,
                   "chan": channel, "now": now})

        if cli_tag:
            await session.execute(text("""
                INSERT INTO github.cli_catalog
                    (tag, sdk_tag, devnet_tag, channel, label, is_active, added_at)
                VALUES (:tag, :sdk_tag, :devnet_tag, :chan, :tag, true, :now)
                ON CONFLICT (tag) DO UPDATE SET
                    sdk_tag    = COALESCE(EXCLUDED.sdk_tag,    github.cli_catalog.sdk_tag),
                    devnet_tag = COALESCE(EXCLUDED.devnet_tag, github.cli_catalog.devnet_tag)
            """), {"tag": cli_tag, "sdk_tag": sdk_tag, "devnet_tag": devnet_tag,
                   "chan": channel, "now": now})

        await session.execute(text("""
            INSERT INTO github.release_catalog
                (tag, cli_tag, node_major_version, channel, label, is_active,
                 added_at, published_at, downloads, body, html_url)
            VALUES
                (:tag, :cli_tag, :major, :channel, :label, true,
                 :now, :published_at, :downloads, :body, :html_url)
            ON CONFLICT (tag) DO UPDATE SET
                cli_tag            = COALESCE(EXCLUDED.cli_tag,
                                              github.release_catalog.cli_tag),
                node_major_version = EXCLUDED.node_major_version,
                channel            = EXCLUDED.channel,
                published_at       = EXCLUDED.published_at,
                downloads          = EXCLUDED.downloads,
                body               = EXCLUDED.body,
                html_url           = EXCLUDED.html_url
        """), {
            "tag": tag, "cli_tag": cli_tag, "major": major,
            "channel": channel, "label": tag,
            "now": now, "published_at": published_at,
            "downloads": downloads, "body": body, "html_url": html_url,
        })
        await session.commit()

    log.info(
        "Upserted node %s into release chain "
        "(node_major=%d cli=%s sdk=%s devnet=%s contracts=%s)",
        tag, major, cli_tag, sdk_tag, devnet_tag, contracts_tag,
    )


async def process_release(release: dict, connection: aio_pika.Connection):
    """Full lifecycle for a newly detected rollups-node release."""
    tag = release["tag_name"]
    log.info("Processing new node release: %s", tag)

    async with connection.channel() as channel:
        prev_tag = await _get_previous_tag()

        async with httpx.AsyncClient(timeout=30) as client:
            prs = await _get_prs_for_tag(client, tag, prev_tag)

        await _insert_release(release, prs)
        await _upsert_node_catalog(release)
        await _publish_release_event(channel, release, prs)


# ─────────────────────────────────────────────────────────────────────────────
# Watcher 2 — CLI releases (independent of node release detection)
# ─────────────────────────────────────────────────────────────────────────────

async def _is_cli_already_processed(tag: str) -> bool:
    """Return True if this CLI tag already exists in github.cli_catalog."""
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT tag FROM github.cli_catalog WHERE tag = :tag"),
            {"tag": tag},
        )
        return result.fetchone() is not None


async def _has_any_run_for_tag(node_tag: str) -> bool:
    """
    Return True if orchestrator.runs already has at least one record for
    this node release tag.  Used to decide whether to publish a release
    event after backfilling toolchain data — we only auto-trigger when the
    node has never been run (not even a failed attempt).
    """
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT id FROM orchestrator.runs WHERE release_tag = :tag LIMIT 1"),
            {"tag": node_tag},
        )
        return result.fetchone() is not None


async def _upsert_cli_chain(release: dict) -> str | None:
    """
    Upsert a CLI release and its full toolchain chain into the catalog.

    Steps
    -----
    1.  Parse the release body for SDK version, devnet version,
        contracts version, and the rollups-node version bump mention.
    2.  Upsert leaf → root: contracts_catalog → devnet_catalog →
        sdk_catalog → cli_catalog.
    3.  Find any github.release_catalog row that matches the node version
        bump mentioned in this CLI release body.
    4.  If found and its cli_tag is currently NULL (no toolchain info):
        UPDATE release_catalog.cli_tag to point to this new CLI entry so
        the complete toolchain is resolvable via JOIN from that node tag.

    The cli_tag is only written when it is NULL.  If a node already has a
    cli_tag set, we leave it alone — the operator can use
    PATCH /releases/{tag}/toolchain to update it deliberately.

    Returns the node_tag that was backfilled, or None if no matching node
    release existed in the catalog (or it already had a cli_tag).
    """
    tag     = release["tag_name"]
    body    = (release.get("body") or "")[:5000]
    channel = _derive_channel(tag)
    published_at = _parse_pub(release.get("published_at"))
    downloads    = sum(a.get("download_count", 0) for a in release.get("assets", []))
    html_url     = release.get("html_url", "")
    now          = datetime.now(timezone.utc)

    # ── Parse body for version references ────────────────────────────────────
    sdk_m         = _SDK_IN_BODY_RE.search(body)
    sdk_tag       = f"v{sdk_m.group(1)}"       if sdk_m       else None

    devnet_m      = _DEVNET_IN_BODY_RE.search(body)
    devnet_tag    = devnet_m.group(1)            if devnet_m    else None

    contracts_m   = _CONTRACTS_IN_BODY_RE.search(body)
    contracts_tag = f"v{contracts_m.group(1)}"  if contracts_m else None

    node_bump_m   = _NODE_BUMP_RE.search(body)
    # Normalise to "v" prefix so it matches release_catalog.tag
    node_tag      = f"v{node_bump_m.group(1)}"  if node_bump_m else None

    log.info(
        "CLI release %s — node_bump=%s sdk=%s devnet=%s contracts=%s",
        tag, node_tag, sdk_tag, devnet_tag, contracts_tag,
    )

    async with AsyncSession(engine) as session:
        # ── Leaf nodes first (satisfy FK constraints) ─────────────────────────
        if sdk_tag:
            await session.execute(text("""
                INSERT INTO github.sdk_catalog (tag, channel, label, added_at)
                VALUES (:tag, :chan, :tag, :now)
                ON CONFLICT (tag) DO NOTHING
            """), {"tag": sdk_tag, "chan": channel, "now": now})

        if contracts_tag:
            await session.execute(text("""
                INSERT INTO github.contracts_catalog (tag, channel, label, added_at)
                VALUES (:tag, :chan, :tag, :now)
                ON CONFLICT (tag) DO NOTHING
            """), {"tag": contracts_tag, "chan": channel, "now": now})

        if devnet_tag:
            await session.execute(text("""
                INSERT INTO github.devnet_catalog
                    (tag, contracts_tag, channel, label, added_at)
                VALUES (:tag, :contracts_tag, :chan, :tag, :now)
                ON CONFLICT (tag) DO UPDATE SET
                    contracts_tag = COALESCE(EXCLUDED.contracts_tag,
                                             github.devnet_catalog.contracts_tag)
            """), {"tag": devnet_tag, "contracts_tag": contracts_tag,
                   "chan": channel, "now": now})

        # ── cli_catalog — the main record for this CLI release ────────────────
        await session.execute(text("""
            INSERT INTO github.cli_catalog
                (tag, sdk_tag, devnet_tag, channel, label, is_active,
                 added_at, published_at, downloads, body, html_url)
            VALUES
                (:tag, :sdk_tag, :devnet_tag, :chan, :tag, true,
                 :now, :published_at, :downloads, :body, :html_url)
            ON CONFLICT (tag) DO UPDATE SET
                sdk_tag      = COALESCE(EXCLUDED.sdk_tag,    github.cli_catalog.sdk_tag),
                devnet_tag   = COALESCE(EXCLUDED.devnet_tag, github.cli_catalog.devnet_tag),
                channel      = EXCLUDED.channel,
                published_at = EXCLUDED.published_at,
                downloads    = EXCLUDED.downloads,
                body         = EXCLUDED.body,
                html_url     = EXCLUDED.html_url
        """), {
            "tag": tag, "sdk_tag": sdk_tag, "devnet_tag": devnet_tag,
            "chan": channel, "now": now, "published_at": published_at,
            "downloads": downloads, "body": body, "html_url": html_url,
        })

        # ── Backfill release_catalog.cli_tag for the referenced node release ──
        # Only writes when cli_tag IS NULL — never silently overwrites an
        # already-set toolchain pointer.
        updated_node_tag: str | None = None
        if node_tag:
            result = await session.execute(text("""
                UPDATE github.release_catalog
                SET cli_tag = :cli_tag
                WHERE tag = :node_tag
                  AND cli_tag IS NULL
                RETURNING tag
            """), {"cli_tag": tag, "node_tag": node_tag})
            row = result.fetchone()
            if row:
                updated_node_tag = row[0]
                log.info(
                    "Backfilled release_catalog.cli_tag for node %s → %s",
                    node_tag, tag,
                )
            else:
                # Node may not be in the catalog yet, or already has a cli_tag
                existing = await session.execute(
                    text("SELECT cli_tag FROM github.release_catalog WHERE tag = :t"),
                    {"t": node_tag},
                )
                existing_row = existing.fetchone()
                if existing_row:
                    log.debug(
                        "Node %s already has cli_tag=%s — skipping overwrite with %s",
                        node_tag, existing_row[0], tag,
                    )
                else:
                    log.debug(
                        "CLI %s references node %s not yet in release_catalog — "
                        "cli_tag will be set when the node release is later detected",
                        tag, node_tag,
                    )

        await session.commit()

    return updated_node_tag


async def _fetch_cli_releases(client: httpx.AsyncClient) -> list[dict]:
    """Fetch up to 100 releases from CLI_GITHUB_REPO."""
    url = f"{GH_API}/repos/{CLI_GITHUB_REPO}/releases"
    try:
        resp = await client.get(url, headers=HEADERS, params={"per_page": "100"})
        if resp.status_code in (403, 429):
            log.warning("GitHub rate limit hit fetching CLI releases (HTTP %d)",
                        resp.status_code)
            return []
        if resp.status_code != 200:
            log.warning("Unexpected status %d fetching CLI releases", resp.status_code)
            return []
        _check_rate_limit(resp)
        return resp.json()
    except Exception as exc:
        log.error("Failed to fetch CLI releases: %s", exc)
        return []


async def process_cli_release(release: dict, connection: aio_pika.Connection):
    """
    Process a single newly-detected CLI release.

    Callable from both the periodic poller and the webhook handler so the
    processing logic lives in exactly one place.

    After upserting the chain it checks whether the backfilled node release
    has ever had a run.  If not, it publishes a release event so the
    orchestrator can trigger a properly-toolchained run.
    """
    tag = release["tag_name"]
    log.info("Processing new CLI release: %s", tag)

    updated_node_tag = await _upsert_cli_chain(release)

    if updated_node_tag:
        has_run = await _has_any_run_for_tag(updated_node_tag)
        if not has_run:
            # Node exists in the catalog but has never been run — publish a
            # release event now that the toolchain is fully resolved.
            log.info(
                "Node %s has no prior runs — publishing release event "
                "with updated toolchain from CLI %s",
                updated_node_tag, tag,
            )
            synthetic_release = {
                "tag_name": updated_node_tag,
                "name":     updated_node_tag,
                "body":     f"Toolchain resolved via CLI release {tag}",
                "html_url": release.get("html_url", ""),
                "author":   {},
            }
            async with connection.channel() as channel:
                await _publish_release_event(channel, synthetic_release, prs=[])
        else:
            log.info(
                "Node %s already has runs — catalog backfilled, no auto-trigger",
                updated_node_tag,
            )


async def _poll_cli_once(client: httpx.AsyncClient, connection: aio_pika.Connection):
    """
    Fetch CLI releases from CLI_GITHUB_REPO and process any that are new.

    Only processes CLI releases (tag major version >= 2).  SDK releases
    (v0.x.x from the same repo) populate sdk_catalog via the cli chain
    upsert — they don't carry rollups-node bump references so they cannot
    drive toolchain backfills independently.
    """
    releases = await _fetch_cli_releases(client)
    new_count = 0

    for rel in releases:
        tag = rel.get("tag_name", "").strip()
        if not tag:
            continue

        # Filter: only process CLI releases (v2.x.x), skip SDK tags (v0.x.x)
        try:
            major = int(tag.lstrip("v").split(".")[0])
        except (ValueError, IndexError):
            continue
        if major < 2:
            continue

        if await _is_cli_already_processed(tag):
            continue

        await process_cli_release(rel, connection)
        new_count += 1

    if new_count:
        log.info("CLI poller: processed %d new CLI release(s)", new_count)
    else:
        log.debug("CLI poller: no new CLI releases found")


# ─────────────────────────────────────────────────────────────────────────────
# Watcher 3 — rollups-contracts releases
# ─────────────────────────────────────────────────────────────────────────────

async def _is_contracts_already_processed(tag: str) -> bool:
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT tag FROM github.contracts_catalog WHERE tag = :tag"),
            {"tag": tag},
        )
        return result.fetchone() is not None


async def _get_latest_contracts_release(client: httpx.AsyncClient) -> dict | None:
    try:
        resp = await client.get(
            f"{GH_API}/repos/{CONTRACTS_GITHUB_REPO}/releases/latest", headers=HEADERS
        )
        if resp.status_code == 404:
            log.warning("No releases found for %s", CONTRACTS_GITHUB_REPO)
            return None
        if resp.status_code in (403, 429):
            log.warning("GitHub rate limit hit fetching contracts release (HTTP %d)",
                        resp.status_code)
            return None
        resp.raise_for_status()
        _check_rate_limit(resp)
        return resp.json()
    except Exception as e:
        log.error("Failed to fetch latest contracts release: %s", e)
        return None


async def _upsert_contracts_catalog(release: dict):
    """Upsert a rollups-contracts release into github.contracts_catalog."""
    tag          = release["tag_name"]
    channel_name = _derive_channel(tag)
    downloads    = sum(a.get("download_count", 0) for a in release.get("assets", []))
    published_at = _parse_pub(release.get("published_at"))
    body     = (release.get("body") or "")[:5000]
    html_url = release.get("html_url", "")

    async with AsyncSession(engine) as session:
        await session.execute(text("""
            INSERT INTO github.contracts_catalog
                (tag, channel, downloads, published_at, body, html_url, is_active, added_at)
            VALUES
                (:tag, :channel, :downloads, :published_at, :body, :html_url, true, now())
            ON CONFLICT (tag) DO UPDATE SET
                channel      = EXCLUDED.channel,
                downloads    = EXCLUDED.downloads,
                published_at = EXCLUDED.published_at,
                body         = EXCLUDED.body,
                html_url     = EXCLUDED.html_url,
                is_active    = EXCLUDED.is_active
        """), {
            "tag": tag, "channel": channel_name, "downloads": downloads,
            "published_at": published_at, "body": body, "html_url": html_url,
        })
        await session.commit()
    log.info("Upserted %s into contracts_catalog", tag)


async def _poll_contracts_once(client: httpx.AsyncClient):
    """Poll the contracts repo for a new release and upsert it if not yet seen."""
    release = await _get_latest_contracts_release(client)
    if not release:
        return
    tag = release["tag_name"]
    if await _is_contracts_already_processed(tag):
        log.debug("Contracts release %s already processed", tag)
        return
    log.info("New contracts release detected: %s", tag)
    await _upsert_contracts_catalog(release)


# ─────────────────────────────────────────────────────────────────────────────
# Main poll loop
# ─────────────────────────────────────────────────────────────────────────────

async def run_poller():
    log.info(
        "Poller starting — node=%s  cli=%s (enabled=%s)  contracts=%s  interval=%ds",
        GITHUB_REPO, CLI_GITHUB_REPO, CLI_POLL_ENABLED,
        CONTRACTS_GITHUB_REPO, POLL_INTERVAL,
    )

    connection = await aio_pika.connect_robust(RABBITMQ_URL)

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                # ── Watcher 1: rollups-node ───────────────────────────────────
                release = await _get_latest_release(client)
                if release:
                    tag = release["tag_name"]
                    if not await _is_node_release_already_processed(tag):
                        await process_release(release, connection)
                    else:
                        log.debug("Node release %s already processed", tag)

                # ── Watcher 2: CLI (independent) ──────────────────────────────
                if CLI_POLL_ENABLED:
                    await _poll_cli_once(client, connection)

                # ── Watcher 3: rollups-contracts ──────────────────────────────
                await _poll_contracts_once(client)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Poller error: %s", e, exc_info=True)

            await asyncio.sleep(POLL_INTERVAL)

    await connection.close()
    log.info("Poller stopped")
