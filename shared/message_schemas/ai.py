"""
shared/message_schemas/ai.py
Messages on rvp.ai exchange:
  - ai.requests  ← AISessionRequest / PRAnalysisRequest  (orchestrator → ai-agent)
  - ai.results   ← AISessionEvent / PRAnalysisResult     (ai-agent → orchestrator)
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


class AIMode(str, Enum):
    AUTONOMOUS    = "autonomous"
    COLLABORATIVE = "collaborative"
    INTERACTIVE   = "interactive"


class AISessionRequest(BaseModel):
    """
    Published to: rvp.ai → ai.requests
    Consumer:     ai-agent
    Kicks off a new AI session in one of the three modes.
    """
    event_id:    str = Field(default_factory=_uuid)
    run_id:      str
    service:     str = "orchestrator"
    ts:          datetime = Field(default_factory=_now)
    # Session config
    session_id:  str = Field(default_factory=_uuid)
    sandbox_id:  str
    mode:        AIMode
    goal:        Optional[str] = None          # autonomous mode goal
    base_test_id: Optional[str] = None         # collaborative mode starting test
    created_by:  Optional[str] = None
    # Release context for the assembler
    release_tag: str
    pr_summaries: Optional[List[str]] = None
    changelog:   Optional[str] = None


class AISessionEventType(str, Enum):
    STARTED   = "started"
    TOOL_CALL = "tool_call"
    FINDING   = "finding"
    COMPLETED = "completed"
    FAILED    = "failed"
    ABORTED   = "aborted"


class AISessionEvent(BaseModel):
    """
    Published to: rvp.ai → ai.results
    Consumer:     orchestrator, dashboard (via Redis pub/sub)
    Streamed continuously during a session.
    """
    event_id:    str = Field(default_factory=_uuid)
    run_id:      str
    session_id:  str
    service:     str = "ai-agent"
    ts:          datetime = Field(default_factory=_now)
    event_type:  AISessionEventType
    # Event-specific payload
    text_delta:  Optional[str] = None          # streaming text chunk
    tool_name:   Optional[str] = None          # tool_call event
    tool_input:  Optional[Dict[str, Any]] = None
    tool_output: Optional[Any] = None
    finding:     Optional[Dict[str, Any]] = None  # finding event
    # Final summary (completed event)
    total_tokens:     Optional[int] = None
    tool_call_count:  Optional[int] = None
    findings_count:   Optional[int] = None


class PRAnalysisRequest(BaseModel):
    """
    Published to: rvp.ai → ai.requests  (releases.ai-agent consumer)
    Consumer:     ai-agent
    Requests AI analysis of a new release's PRs and changelog.
    """
    event_id:    str = Field(default_factory=_uuid)
    run_id:      Optional[str] = None
    service:     str = "github-watcher"
    ts:          datetime = Field(default_factory=_now)
    release_tag: str
    pr_numbers:  List[int] = Field(default_factory=list)
    pr_summaries: List[str] = Field(default_factory=list)
    changelog:   Optional[str] = None


class PRAnalysisResult(BaseModel):
    """
    Published to: rvp.ai → ai.results
    Consumer:     orchestrator
    """
    event_id:      str = Field(default_factory=_uuid)
    run_id:        Optional[str] = None
    service:       str = "ai-agent"
    ts:            datetime = Field(default_factory=_now)
    release_tag:   str
    coverage_gaps: List[Dict[str, Any]] = Field(default_factory=list)
    suggestions:   List[Dict[str, Any]] = Field(default_factory=list)
    raw_response:  Optional[str] = None
