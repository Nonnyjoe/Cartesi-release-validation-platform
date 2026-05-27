"""
services/sandbox-manager/main.py
Entry point — starts the sandbox queue consumer with graceful shutdown.

Fix 5 — SIGTERM/SIGINT handler:
  On signal, the consumer stops accepting new messages and drain() waits
  for all in-flight sandbox _handle tasks to complete (up to 120s) before
  the process exits.  This ensures a graceful rolling deploy or container
  stop does not leave dangling Docker resources.
"""
import asyncio
import logging
import signal

from consumers.sandbox_queue import SandboxQueueConsumer

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sandbox-manager")


async def main():
    log.info("Sandbox Manager starting...")
    consumer = SandboxQueueConsumer()
    await consumer.start()
    log.info("Sandbox Manager ready — consuming sandbox.queue")

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _handle_signal():
        log.info("Shutdown signal received — stopping consumer and draining tasks…")
        stop_event.set()

    loop.add_signal_handler(signal.SIGTERM, _handle_signal)
    loop.add_signal_handler(signal.SIGINT,  _handle_signal)

    consumer_task = asyncio.create_task(consumer.run())

    # Wait for either the consumer to exit or a shutdown signal
    done, _ = await asyncio.wait(
        [consumer_task, asyncio.create_task(stop_event.wait())],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Cancel the queue iterator so no new messages are delivered
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass

    # Give in-flight sandbox tasks time to finish their teardown
    await consumer.drain(timeout=120)
    await consumer.stop()
    log.info("Sandbox Manager stopped cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
