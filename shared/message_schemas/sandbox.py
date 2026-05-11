"""
shared/message_schemas/sandbox.py
Messages on rvp.sandbox exchange:
  - sandbox.queue   ← SandboxRequest  (orchestrator → sandbox-manager)
  - sandbox.events  ← SandboxEvent    (sandbox-manager → orchestrator / test-runner)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class MessageEnvelope(BaseModel):
    """Standard envelope shared by every RabbitMQ message in the platform."""
    event_id: str = Field(default_factory=_uuid)
    run_id:   str = Field(default_factory=_uuid)
    service:  str
    ts:       datetime = Field(default_factory=_now)
    payload:  Dict[str, Any] = Field(default_factory=dict)


class SandboxRequest(BaseModel):
    """
    Published to: rvp.sandbox → sandbox.queue  (priority queue)
    Consumer:     sandbox-manager
    """
    event_id:    str = Field(default_factory=_uuid)
    run_id:      str
    service:     str = "orchestrator"
    ts:          datetime = Field(default_factory=_now)
    # Sandbox-specific fields
    release_tag: str
    image_tag:   str
    priority:    int = 5          # 9=auto, 5=user, 1=scheduled
    resource_limits: Dict[str, Any] = Field(
        default_factory=lambda: {"cpu": 2, "memory": "4g"}
    )
    requested_by: Optional[str] = None


class SandboxEventType(str, Enum):
    PROVISIONING = "provisioning"
    READY        = "ready"
    RUNNING      = "running"
    TEARDOWN     = "teardown"
    CLOSED       = "closed"
    FAILED       = "failed"


class SandboxEvent(BaseModel):
    """
    Published to: rvp.sandbox → sandbox.events
    Consumer:     orchestrator, test-runner, ai-agent
    """
    event_id:      str = Field(default_factory=_uuid)
    run_id:        str
    sandbox_id:    str
    service:       str = "sandbox-manager"
    ts:            datetime = Field(default_factory=_now)
    event_type:    SandboxEventType
    # Populated when READY:
    anvil_port:    Optional[int] = None
    node_port:     Optional[int] = None
    graphql_port:  Optional[int] = None
    docker_network: Optional[str] = None
    container_ids: Optional[List[str]] = None
    # Populated when FAILED:
    failure_reason: Optional[str] = None
