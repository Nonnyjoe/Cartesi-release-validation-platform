"""
services/ai-agent/main.py
Entry point — starts all AI agent consumers concurrently.
"""
import asyncio
import logging

from consumers.session_requests import SessionRequestConsumer
from consumers.pr_analysis import PRAnalysisConsumer

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ai-agent")


async def main():
    log.info("AI Agent starting...")

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
