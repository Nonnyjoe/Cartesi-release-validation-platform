"""
services/ai-agent/consumers/pr_analysis.py
Consumes releases.ai-agent queue.
For each new GitHub release, asks Claude to analyse PRs and changelog,
identify coverage gaps, and suggest new test definitions.
"""
import asyncio
import json
from tools.github_pr import create_github_pr
import logging
import os
import uuid
from datetime import datetime, timezone

import aio_pika
import anthropic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from publishers.session_events import publish_session_event

log = logging.getLogger("ai-agent.consumer.pr_analysis")

RABBITMQ_URL    = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")
DATABASE_URL    = os.environ.get("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL           = "claude-opus-4-6"

engine       = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class PRAnalysisConsumer:
    def __init__(self):
        self._connection = None
        self._channel    = None
        self._client     = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    async def start(self):
        self._connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self._channel    = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=2)

    async def run(self):
        queue = await self._channel.get_queue("releases.ai-agent")
        log.info("AI Agent consuming releases.ai-agent...")
        async with queue.iterator() as q:
            async for message in q:
                async with message.process():
                    try:
                        await self._handle(json.loads(message.body))
                    except Exception as exc:
                        log.exception("Error in PR analysis: %s", exc)

    async def _handle(self, msg: dict):
        release_tag  = msg.get("release_tag", "unknown")
        pr_summaries = msg.get("pr_summaries", [])
        changelog    = msg.get("changelog", "")
        log.info("Analysing release %s (%d PRs)", release_tag, len(pr_summaries))

        prompt = self._build_analysis_prompt(release_tag, pr_summaries, changelog)

        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_response = response.content[0].text

        # Parse structured output
        coverage_gaps, suggestions = self._parse_analysis(raw_response)

        # Save to ai.analyses
        analysis_id = str(uuid.uuid4())
        async with SessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO ai.analyses
                      (id, release_tag, pr_numbers, changelog, coverage_gaps, suggestions, raw_response)
                    VALUES (:id, :tag, :prs, :cl, :gaps::jsonb, :sugg::jsonb, :raw)
                """),
                {
                    "id":   analysis_id,
                    "tag":  release_tag,
                    "prs":  msg.get("pr_numbers", []),
                    "cl":   changelog,
                    "gaps": json.dumps(coverage_gaps),
                    "sugg": json.dumps(suggestions),
                    "raw":  raw_response,
                },
            )
            await db.commit()

        # Save suggested test actions for human review
        for suggestion in suggestions:
            async with SessionLocal() as db:
                await db.execute(
                    text("""
                        INSERT INTO ai.suggested_test_actions
                          (id, analysis_id, definition_raw, status)
                        VALUES (:id, :analysis_id, :raw, 'pending')
                    """),
                    {
                        "id":          str(uuid.uuid4()),
                        "analysis_id": analysis_id,
                        "raw":         suggestion.get("definition_raw", ""),
                    },
                )
                await db.commit()

        # Publish result
        await publish_session_event({
            "event_id":      str(uuid.uuid4()),
            "service":       "ai-agent",
            "ts":            datetime.now(tz=timezone.utc).isoformat(),
            "event_type":    "pr_analysis_complete",
            "release_tag":   release_tag,
            "analysis_id":   analysis_id,
            "gaps_found":    len(coverage_gaps),
            "suggestions":   len(suggestions),
        })

        # Auto-PR: if any suggestion has high confidence and AUTO_PR_ENABLED
        if os.getenv("AUTO_PR_ENABLED", "false").lower() == "true" and suggestions:
            high_conf = [s for s in suggestions if s.get("confidence", 0) >= 0.85]
            if high_conf:
                files = [
                    {
                        "path": f"tests/definitions/ai-{s['action_type'].replace(' ', '-')}-{i}.md",
                        "content": s.get("test_definition_yaml", f"---\nname: {s['description']}\n---\n"),
                    }
                    for i, s in enumerate(high_conf)
                ]
                tag = release_data.get("tag_name", "unknown")
                pr_result = await create_github_pr({
                    "branch": f"auto-test/{tag}-suggestions",
                    "files": files,
                    "title": f"AI-suggested tests for {tag}",
                    "body": (
                        f"## AI Coverage Gap Analysis — {tag}\n\n"
                        + "\n\n".join(
                            f"### {s['description']}\n{s.get('rationale', '')}"
                            for s in high_conf
                        )
                    ),
                }, {})
                log.info("Auto-PR result: %s", pr_result)

        log.info("PR analysis complete for %s: %d gaps, %d suggestions",
                 release_tag, len(coverage_gaps), len(suggestions))

    def _build_analysis_prompt(self, release_tag: str, pr_summaries: list, changelog: str) -> str:
        prs_text = "\n".join(f"- {s}" for s in pr_summaries) if pr_summaries else "No PR summaries provided."
        return f"""You are a Cartesi rollups node test architect. Analyse this release and identify testing gaps.

Release: {release_tag}

Changelog:
{changelog or "Not provided."}

PR Summaries:
{prs_text}

Your task:
1. Identify components or behaviours changed in this release that may not be covered by existing tests.
2. For each gap, suggest a new test definition in YAML frontmatter + Markdown format.

Respond in this exact JSON format:
{{
  "coverage_gaps": [
    {{"component": "...", "description": "...", "risk": "high|medium|low"}}
  ],
  "suggestions": [
    {{
      "slug": "test-slug",
      "rationale": "Why this test is needed",
      "definition_raw": "---\\nid: test-slug\\nname: ...\\n---\\n## Description\\n..."
    }}
  ]
}}"""

    def _parse_analysis(self, raw: str) -> tuple[list, list]:
        try:
            import re
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("coverage_gaps", []), data.get("suggestions", [])
        except Exception as exc:
            log.warning("Failed to parse analysis JSON: %s", exc)
        return [], []

    async def stop(self):
        if self._connection:
            await self._connection.close()
