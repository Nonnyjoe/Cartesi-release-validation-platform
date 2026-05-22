"""
tests/conftest.py
Project-wide test configuration.
Sets environment variables and shared sys.path entries before any service
module is imported.  Individual test packages add their own service paths.
"""
import os
import sys

# ── Env vars required by module-level code in service files ──────────────────
# (db.py reads DATABASE_URL at import time; consumer modules read RABBITMQ_URL)
os.environ.setdefault("DATABASE_URL",  "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("RABBITMQ_URL",  "amqp://rvp:test@localhost:5672/")
os.environ.setdefault("REDIS_URL",     "redis://localhost:6379")
os.environ.setdefault("SANDBOX_HOST",  "testhost")

# ── Add shared/ so sdk_resolver is importable from all sub-packages ──────────
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
_shared = os.path.join(REPO_ROOT, "shared")
if _shared not in sys.path:
    sys.path.insert(0, _shared)
