"""
services/github-watcher/poller.py

Polls GitHub Releases API on a fixed interval.
Detects new releases by comparing against the `github.releases` DB table.
On a new release:
  1. Fetches associated PRs (capped at 5 to stay within rate limits).
  2. Resolves the SDK version for v2.x releases by scanning cartesi/cli releases.
  3. Inserts a record into `github.releases`.
  4. Upserts the release into `github.release_catalog` with correct image_tag,
     sdk_version, and node_major_version.
  5. Publishes a release event to `rvp.releases` fanout exchange.

NOTE: The sandbox request (run triggering) is handled by the orchestrator's
ReleasesConsumer, which generates the run_id after the event is consumed.
This fixes the race where the sandbox-manager could process a request before
the orchestrator had a matching run row in orchestrator.runs.
"""
import asyncio
import json
import logging
import os
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

GITHUB_TOKEN          = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO           = os.getenv("GITHUB_REPO", "cartesi/rollups-node")
CONTRACTS_GITHUB_REPO = os.getenv("CONTRACTS_GITHUB_REPO", "cartesi/rollups-contracts")
POLL_INTERVAL  = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
RABBITMQ_URL   = os.getenv("RABBITMQ_URL", "amqp://rvp:rvp_secret@rabbitmq:5672/rvp")
DATABASE_URL   = os.getenv("DATABASE_URL", "postgresql+asyncpg://rvp_github:rvp_secret@postgres:5432/rvp")

GH_API = "https://api.github.com"
HEADERS = {
    "Accept":               "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

engine = create_async_engine(DATABASE_URL, echo=False)

RATE_LIMIT_FLOOR = int(os.getenv("RATE_LIMIT_FLOOR", "20"))


def _check_rate_limit(response: httpx.Response) -> bool:
    remaining = int(response.headers.get("X-RateLimit-Remaining", 999))
    if remaining < RATE_LIMIT_FLOOR:
        reset_ts = response.headers.get("X-RateLimit-Reset", "unknown")
        log.warning("GitHub rate limit low: %d remaining, resets at %s", remaining, reset_ts)
        return False
    return True


async def _get_latest_release(client: httpx.AsyncClient) -> dict | None:
    try:
        resp = await client.get(
            f"{GH_API}/repos/{GITHUB_REPO}/releases/latest", headers=HEADERS
        )
        if resp.status_code == 404:
            log.warning("No releases found for %s", GITHUB_REPO)
            return None
        if resp.status_code in (403, 429):
            reset_ts = resp.headers.get("X-RateLimit-Reset", "unknown")
            log.warning("GitHub rate limit hit (HTTP %d). Reset at: %s",
                        resp.status_code, reset_ts)
            return None
        resp.raise_for_status()
        _check_rate_limit(resp)
        return resp.json()
    except Exception as e:
        log.error("Failed to fetch latest release: %s", e)
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

        import re
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


async def _is_already_processed(tag: str) -> bool:
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


async def _upsert_catalog(release: dict):
    """
    Keep the normalized version chain up-to-date when a new rollups-node release
    is detected.  Writes leaf-to-root so FK constraints are satisfied:
      contracts_catalog → devnet_catalog → sdk_catalog → cli_catalog → release_catalog
    """
    tag      = release["tag_name"]
    major    = _major(tag)
    channel  = "alpha" if "alpha" in tag.lower() else "beta" if "beta" in tag.lower() else "stable"
    downloads = sum(a.get("download_count", 0) for a in release.get("assets", []))
    raw_pub  = release.get("published_at")
    published_at = (
        datetime.fromisoformat(raw_pub.replace("Z", "+00:00")) if raw_pub else None
    )
    body     = (release.get("body") or "")[:5000]
    html_url = release.get("html_url", "")

    cli_tag       = None
    sdk_tag       = None
    devnet_tag    = None
    contracts_tag = None

    if major >= 2:
        sdk_version, cli_version, devnet_version, contracts_version = \
            await resolve_all_versions(tag, GITHUB_TOKEN)
        cli_tag       = f"v{cli_version}"    if cli_version    else None
        sdk_tag       = f"v{sdk_version}"    if sdk_version    else None
        devnet_tag    = devnet_version        if devnet_version else None
        contracts_tag = f"v{contracts_version}" if contracts_version else None

    now = datetime.now(timezone.utc)

    async with AsyncSession(engine) as session:
        # Leaf nodes first
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

        # release_catalog stores only cli_tag FK + metadata
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
            "tag":          tag,
            "cli_tag":      cli_tag,
            "major":        major,
            "channel":      channel,
            "label":        tag,
            "now":          now,
            "published_at": published_at,
            "downloads":    downloads,
            "body":         body,
            "html_url":     html_url,
        })
        await session.commit()

    log.info(
        "Upserted %s into release chain "
        "(node_major=%d cli=%s sdk=%s devnet=%s contracts=%s)",
        tag, major, cli_tag, sdk_tag, devnet_tag, contracts_tag,
    )


async def _upsert_contracts_catalog(release: dict):
    """Upsert a rollups-contracts release into github.contracts_catalog."""
    tag          = release["tag_name"]
    channel_name = "alpha" if "alpha" in tag.lower() else "beta" if "beta" in tag.lower() else "stable"
    downloads    = sum(a.get("download_count", 0) for a in release.get("assets", []))
    raw_pub      = release.get("published_at")
    published_at = (
        datetime.fromisoformat(raw_pub.replace("Z", "+00:00")) if raw_pub else None
    )
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
            "tag":          tag,
            "channel":      channel_name,
            "downloads":    downloads,
            "published_at": published_at,
            "body":         body,
            "html_url":     html_url,
        })
        await session.commit()
    log.info("Upserted %s into contracts_catalog", tag)


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
            reset_ts = resp.headers.get("X-RateLimit-Reset", "unknown")
            log.warning("GitHub rate limit hit (HTTP %d) fetching contracts release. Reset at: %s",
                        resp.status_code, reset_ts)
            return None
        resp.raise_for_status()
        _check_rate_limit(resp)
        return resp.json()
    except Exception as e:
        log.error("Failed to fetch latest contracts release: %s", e)
        return None


async def _poll_contracts_once(client: httpx.AsyncClient):
    """Poll the contracts repo for a new release and upsert it if not yet seen."""
    release = await _get_latest_contracts_release(client)
    if not release:
        return
    tag = release["tag_name"]
    if await _is_contracts_already_processed(tag):
        log.debug("Contracts release %s already processed, skipping", tag)
        return
    log.info("New contracts release detected: %s", tag)
    await _upsert_contracts_catalog(release)


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


async def process_release(release: dict, connection: aio_pika.Connection):
    tag = release["tag_name"]
    log.info("Processing new release: %s", tag)

    async with connection.channel() as channel:
        prev_tag = await _get_previous_tag()

        async with httpx.AsyncClient(timeout=30) as client:
            prs = await _get_prs_for_tag(client, tag, prev_tag)

        await _insert_release(release, prs)
        await _upsert_catalog(release)
        await _publish_release_event(channel, release, prs)


async def run_poller():
    log.info("Poller starting — repo=%s interval=%ds", GITHUB_REPO, POLL_INTERVAL)

    connection = await aio_pika.connect_robust(RABBITMQ_URL)

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                release = await _get_latest_release(client)
                if release:
                    tag = release["tag_name"]
                    if not await _is_already_processed(tag):
                        await process_release(release, connection)
                    else:
                        log.debug("Release %s already processed, skipping", tag)

                await _poll_contracts_once(client)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Poller error: %s", e, exc_info=True)

            await asyncio.sleep(POLL_INTERVAL)

    await connection.close()
    log.info("Poller stopped")
