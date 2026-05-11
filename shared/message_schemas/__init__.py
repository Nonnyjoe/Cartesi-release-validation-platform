"""
shared/message_schemas
Pydantic models for all RabbitMQ messages.
Every message shares the standard envelope defined in base.py.
"""
from .sandbox import (
    SandboxRequest,
    SandboxEvent,
    SandboxEventType,
)
from .test import (
    TestCommand,
    TestResult,
    AssertionResult,
)
from .ai import (
    AISessionRequest,
    AISessionEvent,
    PRAnalysisRequest,
    PRAnalysisResult,
)
from .notification import (
    NotificationMessage,
    NotificationEventType,
)

__all__ = [
    "SandboxRequest", "SandboxEvent", "SandboxEventType",
    "TestCommand", "TestResult", "AssertionResult",
    "AISessionRequest", "AISessionEvent", "PRAnalysisRequest", "PRAnalysisResult",
    "NotificationMessage", "NotificationEventType",
]
