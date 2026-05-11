"""
services/test-runner/loader.py
Hot-reloads test definitions from the DB every RELOAD_INTERVAL seconds.
Keeps an in-memory cache so the executor always has the latest definitions
without restarting the service.
"""
import asyncio
import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

log = logging.getLogger("test-runner.loader")

DATABASE_URL = os.environ.get("DATABASE_URL", "").replace(
    "postgresql://", "postgresql+asyncpg://"
)
RELOAD_INTERVAL = int(os.environ.get("DEFINITION_RELOAD_INTERVAL", 30))  # seconds

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class DefinitionLoader:
    def __init__(self):
        self._cache: dict[str, dict] = {}   # definition_id → parsed definition
        self._lock = asyncio.Lock()

    async def get(self, definition_id: str) -> dict | None:
        async with self._lock:
            return self._cache.get(definition_id)

    async def get_all(self) -> list[dict]:
        async with self._lock:
            return list(self._cache.values())

    async def start_hot_reload(self):
        """Background task: periodically refresh definitions from DB."""
        log.info("Definition hot-reload starting (interval=%ds)", RELOAD_INTERVAL)
        while True:
            try:
                await self._reload()
            except Exception as exc:
                log.warning("Definition reload failed: %s", exc)
            await asyncio.sleep(RELOAD_INTERVAL)

    async def _reload(self):
        async with SessionLocal() as db:
            rows = await db.execute(
                text("""
                    SELECT id, slug, name, version, tags, component, priority,
                           timeout_seconds, definition_parsed
                    FROM tests.definitions
                    WHERE is_active = true
                    ORDER BY slug
                """)
            )
            defs = rows.fetchall()

        async with self._lock:
            new_cache = {}
            for row in defs:
                d = dict(row._mapping)
                d["id"] = str(d["id"])
                new_cache[d["id"]] = d
            prev_count = len(self._cache)
            self._cache = new_cache

        if len(new_cache) != prev_count:
            log.info("Definitions reloaded: %d active definitions", len(new_cache))
