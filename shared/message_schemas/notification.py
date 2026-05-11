"""
shared/message_schemas/notification.py
Messages on rvp.notify exchange (fanout):
  - notify.discord    ← NotificationMessage  (any service → notifier)
  - notify.dashboard  ← NotificationMessage  (any service → notifier / dashboard)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class NotificationEventType(str, Enum):
    # Release events
    RELEASE_DETECTED     = "release.detected"
    # Run lifecycle
    RUN_QUEUED           = "run.queued"
    RUN_STARTED          = "run.started"
    RUN_COMPLETED        = "run.completed"
    RUN_FAILED           = "run.failed"
    # Sandbox
    SANDBOX_READY        = "sandbox.ready"
    SANDBOX_FAILED       = "sandbox.failed"
    # Test events
    TEST_PASSED          = "test.passed"
    TEST_FAILED          = "test.failed"
    # AI events
    AI_FINDING           = "ai.finding"
    AI_SESSION_COMPLETED = "ai.session.completed"
    # Generic
    SYSTEM_ALERT         = "system.alert"


class NotificationMessage(BaseModel):
    """
    Published to: rvp.notify (fanout → notify.discord + notify.dashboard)
    Consumer:     notifier service (Discord webhook + dashboard push)
    """
    event_id:    str = Field(default_factory=_uuid)
    run_id:      Optional[str] = None
    service:     str
    ts:          datetime = Field(default_factory=_now)
    event_type:  NotificationEventType
    title:       str
    description: Optional[str] = None
    color:       Optional[int] = None       # Discord embed colour (int)
    fields:      Dict[str, Any] = Field(default_factory=dict)
    url:         Optional[str] = None       # Deep-link into dashboard
    # Priority hint for Discord formatting
    is_error:    bool = False
    is_success:  bool = False
