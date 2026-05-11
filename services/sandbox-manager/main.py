"""
services/sandbox-manager/main.py
Entry point — starts the sandbox queue consumer.
"""
import asyncio
import logging

from consumers.sandbox_queue import SandboxQueueConsumer

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sandbox-manager")


async def main():
    log.info("Sandbox Manager starting...")
    consumer = SandboxQueueConsumer()
    await consumer.start()
    log.info("Sandbox Manager ready — consuming sandbox.queue")
    await consumer.run()


if __name__ == "__main__":
    asyncio.run(main())
