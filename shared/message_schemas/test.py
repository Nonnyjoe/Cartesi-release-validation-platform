"""
shared/message_schemas/test.py
Messages on rvp.tests exchange:
  - tests.commands  ← TestCommand    (orchestrator → test-runner)
  - tests.results   ← TestResult     (test-runner → orchestrator)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class TestCommand(BaseModel):
    """
    Published to: rvp.tests → tests.commands
    Consumer:     test-runner
    """
    event_id:           str = Field(default_factory=_uuid)
    run_id:             str
    sandbox_id:         str
    service:            str = "orchestrator"
    ts:                 datetime = Field(default_factory=_now)
    # Test target
    definition_id:      str
    definition_version: int
    definition_slug:    str
    # Sandbox connection info (passed from SandboxEvent.READY)
    anvil_port:         int
    node_port:          int
    graphql_port:       int
    docker_network:     str
    # Optional AI override (collaborative/interactive mode)
    payload_override:   Optional[Dict[str, Any]] = None
    ai_session_id:      Optional[str] = None


class AssertionResult(BaseModel):
    """Result of a single assertion within a test."""
    assertion_type: str             # graphql | log_contains | http_status | chain_tx | voucher
    passed:         bool
    expected:       Optional[Any] = None
    actual:         Optional[Any] = None
    detail:         Optional[str] = None
    duration_ms:    Optional[int] = None


class TestResult(BaseModel):
    """
    Published to: rvp.tests → tests.results
    Consumer:     orchestrator
    """
    event_id:           str = Field(default_factory=_uuid)
    run_id:             str
    sandbox_id:         str
    service:            str = "test-runner"
    ts:                 datetime = Field(default_factory=_now)
    # Result data
    result_id:          str = Field(default_factory=_uuid)
    definition_id:      str
    definition_version: int
    definition_slug:    str
    status:             str       # passed | failed | error | timeout | skipped
    duration_ms:        int
    assertion_results:  List[AssertionResult] = Field(default_factory=list)
    logs:               Optional[str] = None
    error_message:      Optional[str] = None
    started_at:         Optional[datetime] = None
    completed_at:       Optional[datetime] = None
