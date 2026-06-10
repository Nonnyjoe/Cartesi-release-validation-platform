"""
services/ai-agent/main.py
Entry point — starts all AI agent consumers concurrently.
"""
import asyncio
import logging
import sys
from pathlib import Path

from consumers.session_requests import SessionRequestConsumer
from consumers.pr_analysis import PRAnalysisConsumer

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ai-agent")


async def _refresh_test_catalog():
    """Regenerate context/sources/project/test-catalog.md from tests.definitions.

    Best-effort: the agent still starts (with a stale or absent catalog) if the
    DB isn't reachable yet. The assembler tolerates a missing file.
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent / "scripts"))
        import build_test_catalog  # noqa: PLC0415
        await build_test_catalog.main()
        log.info("Test catalog refreshed")
    except Exception as exc:
        log.warning("Could not refresh test catalog (continuing): %s", exc)


async def main():
    log.info("AI Agent starting...")

    await _refresh_test_catalog()

    session_consumer = SessionRequestConsumer()
    pr_consumer      = PRAnalysisConsumer()

    await asyncio.gather(
        session_consumer.start(),
        pr_consumer.start(),
    )

    log.info("AI Agent ready — consuming ai.requests and releases.ai-agent")

    await asyncio.gather(
        session_consumer.run(),
        pr_consumer.run(),
    )


if __name__ == "__main__":
    asyncio.run(main())
