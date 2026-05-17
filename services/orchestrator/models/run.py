"""
services/orchestrator/models/run.py
ORM models for orchestrator.runs, orchestrator.run_events, and orchestrator.run_logs.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Column, String, Integer, SmallInteger, Numeric, ARRAY,
    TIMESTAMP, Boolean, Enum as SAEnum, ForeignKey, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from db import Base


def _now():
    return datetime.now(tz=timezone.utc)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = {"schema": "orchestrator"}

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_tag       = Column(String, nullable=False)
    image_tag         = Column(String, nullable=False)
    suite_ids         = Column(ARRAY(UUID(as_uuid=True)))
    status            = Column(SAEnum("queued", "provisioning", "running", "completed", "failed", "warning", "cancelled", name="run_status", create_type=False), nullable=False, default="queued")
    priority          = Column(SmallInteger, nullable=False, default=5)
    triggered_by      = Column(SAEnum("github_release", "user", "scheduled", name="triggered_by_type", create_type=False), nullable=False)
    triggered_by_user = Column(String)
    queued_at         = Column(TIMESTAMP(timezone=True), default=_now)
    started_at        = Column(TIMESTAMP(timezone=True))
    completed_at      = Column(TIMESTAMP(timezone=True))
    pass_rate         = Column(Numeric(5, 2))
    report            = Column(JSONB)
    metadata_         = Column("metadata", JSONB, default=dict)
    # Application registry — populated when a run is triggered with an app_id
    app_id            = Column(UUID(as_uuid=True), ForeignKey("tests.applications.id", use_alter=True), nullable=True)
    app_address       = Column(String, nullable=True)  # Ethereum address of deployed app contract

    events = relationship("RunEvent", back_populates="run", cascade="all, delete-orphan")


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = {"schema": "orchestrator"}

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id     = Column(UUID(as_uuid=True), ForeignKey("orchestrator.runs.id"), nullable=False)
    event_type = Column(String, nullable=False)
    payload    = Column(JSONB)
    ts         = Column(TIMESTAMP(timezone=True), default=_now)

    run = relationship("Run", back_populates="events", foreign_keys=[run_id])


class RunLog(Base):
    """
    Persistent log lines for a run.  Written by the orchestrator consumer when
    it receives log_batch events from the sandbox-manager or test-runner.

    The BIGSERIAL primary key serves as the ordering cursor; keyset pagination
    on (run_id, id) is efficient and correct under concurrent inserts.
    """
    __tablename__ = "run_logs"
    __table_args__ = {"schema": "orchestrator"}

    id      = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id  = Column(UUID(as_uuid=True), ForeignKey("orchestrator.runs.id", ondelete="CASCADE"),
                     nullable=False, index=False)   # covered by the composite index
    source  = Column(String, nullable=False)         # "advancer", "anvil", "build", "test:uuid", …
    level   = Column(String, nullable=False, default="info")
    message = Column(String, nullable=False)
    ts      = Column(TIMESTAMP(timezone=True), default=_now)
