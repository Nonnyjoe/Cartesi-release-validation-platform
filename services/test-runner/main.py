"""
services/test-runner/main.py
Starts the test command consumer and the hot-reload loader.
"""
import asyncio
import logging

from consumers.test_commands import TestCommandConsumer
from loader import DefinitionLoader

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test-runner")


async def main():
    log.info("Test Runner starting...")
    loader   = DefinitionLoader()
    consumer = TestCommandConsumer(loader)

    await asyncio.gather(
        loader.start_hot_reload(),
        consumer.start_consuming(),
    )


if __name__ == "__main__":
    asyncio.run(main())
