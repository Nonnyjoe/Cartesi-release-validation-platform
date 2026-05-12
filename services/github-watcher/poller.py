"""
services/github-watcher/poller.py

Polls GitHub Releases API on a fixed interval.
Detects new releases by comparing against the `github.releases` DB table.
On a new release:
  1. Fetches associated PRs and extracts their summaries.
  2. Inserts a record into `github.releases`.
  3. Publishes a release event to `rvp.releases` fanout exchange.
  4. Triggers a high-priority validation run via `sandbox.queue`.
  5. Updates `github.releases.run_triggered = true` with the new run_id.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import aio_pika
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text

log = logging.getLogger("github-watcher.poller")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "cartesi/rollups-node")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://rvp:rvp_secret@rabbitmq:5672/rvp")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://rvp_github:rvp_secret@postgres:5432/rvp")
NODE_VERSION_OVERRIDE = os.getenv("NODE_VERSION_OVERRIDE", "")

GH_API = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

engine = create_async_engine(DATABASE_URL, echo=False)


async def _get_latest_release(client: httpx.AsyncClient) -> dict | None:
    try:
        resp = await client.get(f"{GH_API}/repos/{GITHUB_REPO}/releases/latest", headers=HEADERS)
        if resp.status_code == 404:
            log.warning("No releases found for %s", GITHUB_REPO)
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error("Failed to fetch latest release: %s", e)
        return None


async def _get_prs_for_tag(client: httpx.AsyncClient, tag: str, prev_tag: str | None) -> list[dict]:
    """Return a list of PR metadata merged between prev_tag and tag."""
    try:
        if prev_tag:
            compare_url = f"{GH_API}/repos/{GITHUB_REPO}/compare/{prev_tag}...{tag}"
            resp = await client.get(compare_url, headers=HEADERS)
            if resp.status_code != 200:
                return []
            data = resp.json()
            commits = data.get("commits", [])
        else:
            commits = []

        # Extract PR numbers from commit messages
        import re
        pr_numbers = set()
        for commit in commits:
            msg = commit.get("commit", {}).get("message", "")
            matches = re.findall(r"#(\d+)", msg)
            pr_numbers.update(matches)

        prs = []
        for pr_num in list(pr_numbers)[:20]:  # cap at 20 PRs
            try:
                pr_resp = await client.get(
                    f"{GH_API}/repos/{GITHUB_REPO}/pulls/{pr_num}", headers=HEADERS
                )
                if pr_resp.status_code == 200:
                    pr = pr_resp.json()
                    prs.append({
                        "number": pr.get("number"),
                        "title": pr.get("title"),
                        "body": (pr.get("body") or "")[:500],
                        "author": pr.get("user", {}).get("login"),
                        "labels": [lb["name"] for lb in pr.get("labels", [])],
                    })
            except Exception:
                pass
        return prs
    except Exception as e:
        log.error("Failed to fetch PRs: %s", e)
        return []


async def _is_already_processed(tag: str) -> bool:
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT release_id FROM github.releases WHERE tag_name = :tag"),
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


async def _insert_release(release: dict, run_id: str, prs: list[dict]) -> str:
    release_id = str(uuid.uuid4())
    async with AsyncSession(engine) as session:
        await session.execute(
            text("""
                INSERT INTO github.releases
                    (release_id, tag_name, release_name, body, published_at,
                     author, pr_summary, run_id, run_triggered)
                VALUES
                    (:id, :tag, :name, :body, :pub_at,
                     :author, :pr_summary::jsonb, :run_id, true)
                ON CONFLICT (tag_name) DO NOTHING
            """),
            {
                "id": release_id,
                "tag": release["tag_name"],
                "name": release.get("name", release["tag_name"]),
                "body": (release.get("body") or "")[:5000],
                "pub_at": datetime.fromisoformat(
                    release["published_at"].replace("Z", "+00:00")
                ),
                "author": release.get("author", {}).get("login", "unknown"),
                "pr_summary": json.dumps(prs),
                "run_id": run_id,
            },
        )
        await session.commit()
    return release_id


async def _publish_release_event(channel: aio_pika.Channel, release: dict, run_id: str, prs: list[dict]):
    exchange = await channel.get_exchange("rvp.releases")
    payload = {
        "event_id": str(uuid.uuid4()),
        "run_id": run_id,
        "service": "github-watcher",
        "ts": datetime.now(timezone.utc).isoformat(),
        "tag_name": release["tag_name"],
        "release_name": release.get("name", release["tag_name"]),
        "body": (release.get("body") or "")[:2000],
        "author": release.get("author", {}).get("login", "unknown"),
        "prs": prs,
        "html_url": release.get("html_url", ""),
    }
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
        ),
        routing_key="",  # fanout — routing key ignored
    )
    log.info("Published release event for %s", release["tag_name"])


async def _trigger_run(channel: aio_pika.Channel, release: dict) -> str:
    """Publish a SandboxRequest to the priority sandbox queue and return the run_id."""
    run_id = str(uuid.uuid4())
    node_version = NODE_VERSION_OVERRIDE or release["tag_name"].lstrip("v")
    queue = await channel.get_queue("sandbox.queue")
    payload = {
        "event_id": str(uuid.uuid4()),
        "run_id": run_id,
        "service": "github-watcher",
        "ts": datetime.now(timezone.utc).isoformat(),
        "node_version": node_version,
        "pr_number": None,
        "repo_url": f"https://github.com/{GITHUB_REPO}",
        "triggered_by": "github-watcher",
        "priority": 9,
    }
    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            priority=9,
        ),
        routing_key="sandbox.queue",
    )
    log.info("Triggered run %s for release %s", run_id, release["tag_name"])
    return run_id


async def process_release(release: dict, connection: aio_pika.Connection):
    tag = release["tag_name"]
    log.info("Processing new release: %s", tag)

    async with connection.channel() as channel:
        prev_tag = await _get_previous_tag()

        async with httpx.AsyncClient(timeout=30) as client:
            prs = await _get_prs_for_tag(client, tag, prev_tag)

        run_id = await _trigger_run(channel, release)
        await _insert_release(release, run_id, prs)
        await _publish_release_event(channel, release, run_id, prs)


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
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Poller error: %s", e, exc_info=True)

            await asyncio.sleep(POLL_INTERVAL)

    await connection.close()
    log.info("Poller stopped")
