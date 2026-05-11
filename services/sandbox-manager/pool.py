"""
services/sandbox-manager/pool.py
Tracks active sandboxes and enforces MAX_SANDBOXES cap.
Thread-safe via asyncio.Lock.
"""
import asyncio
import logging
import os

log = logging.getLogger("sandbox-manager.pool")

MAX_SANDBOXES = int(os.environ.get("MAX_SANDBOXES", 5))


class SandboxPool:
    """
    Tracks how many sandboxes are currently active (provisioning or running).
    The consumer must call acquire() before provisioning and release() after teardown.
    """

    def __init__(self):
        self._active: dict[str, dict] = {}   # sandbox_id → metadata
        self._lock = asyncio.Lock()
        self._slot_available = asyncio.Event()
        self._slot_available.set()            # initially slots are free

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def has_capacity(self) -> bool:
        return self.active_count < MAX_SANDBOXES

    async def acquire(self, sandbox_id: str, run_id: str) -> bool:
        """
        Try to claim a slot.  Returns True if acquired, False if at capacity.
        Callers should await wait_for_slot() before calling acquire() if they
        want to block until a slot opens.
        """
        async with self._lock:
            if not self.has_capacity:
                return False
            self._active[sandbox_id] = {"run_id": run_id, "sandbox_id": sandbox_id}
            if not self.has_capacity:
                self._slot_available.clear()
            log.info("Pool: acquired slot for sandbox %s (%d/%d)",
                     sandbox_id, self.active_count, MAX_SANDBOXES)
            return True

    async def release(self, sandbox_id: str):
        async with self._lock:
            self._active.pop(sandbox_id, None)
            self._slot_available.set()
            log.info("Pool: released slot for sandbox %s (%d/%d)",
                     sandbox_id, self.active_count, MAX_SANDBOXES)

    async def wait_for_slot(self):
        """Block until a slot is available."""
        while not self.has_capacity:
            self._slot_available.clear()
            await self._slot_available.wait()


# Singleton
pool = SandboxPool()
