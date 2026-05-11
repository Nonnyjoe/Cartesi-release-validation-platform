"""
services/orchestrator/models/result.py
Read-only ORM model for tests.results (orchestrator has SELECT only).
"""
import uuid
from sqlalchemy import Column, String, Integer, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from db import Base


class TestResult(Base):
    __tablename__ = "results"
    __table_args__ = {"schema": "tests"}

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id               = Column(UUID(as_uuid=True), nullable=False)
    sandbox_id           = Column(UUID(as_uuid=True), nullable=False)
    definition_id        = Column(UUID(as_uuid=True), nullable=False)
    definition_version   = Column(Integer, nullable=False)
    status               = Column(String, nullable=False)
    duration_ms          = Column(Integer)
    assertion_results    = Column(JSONB)
    logs                 = Column(String)
    error_message        = Column(String)
    started_at           = Column(TIMESTAMP(timezone=True))
    completed_at         = Column(TIMESTAMP(timezone=True))
