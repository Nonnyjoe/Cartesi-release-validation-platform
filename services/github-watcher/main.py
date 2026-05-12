"""
services/github-watcher/main.py

Entry point — runs two concurrent tasks:
  1. The release poller (asyncio loop, every POLL_INTERVAL_SECONDS)
  2. The webhook FastAPI server (uvicorn, port 8001)

Both share the same asyncio event loop via asyncio.gather().
"""
import asyncio
import logging
import os

import uvicorn

from poller import run_poller
from webhook_handler import app as webhook_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
log = logging.getLogger("github-watcher")

WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8001"))
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")


async def run_webhook_server():
    config = uvicorn.Config(
        webhook_app,
        host=WEBHOOK_HOST,
        port=WEBHOOK_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    log.info("GitHub Watcher starting up")
    await asyncio.gather(
        run_poller(),
        run_webhook_server(),
        return_exceptions=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
