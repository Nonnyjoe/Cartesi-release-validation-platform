"""
services/orchestrator/models/run.py
ORM model for orchestrator.runs and orchestrator.run_events.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, SmallInteger, Numeric, ARRAY,
    TIMESTAMP, Boolean, Enum as SAEnum, text,
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
    status            = Column(String, nullable=False, default="queued")
    priority          = Column(SmallInteger, nullable=False, default=5)
    triggered_by      = Column(String, nullable=False)
    triggered_by_user = Column(String)
    queued_at         = Column(TIMESTAMP(timezone=True), default=_now)
    started_at        = Column(TIMESTAMP(timezone=True))
    completed_at      = Column(TIMESTAMP(timezone=True))
    pass_rate         = Column(Numeric(5, 2))
    report            = Column(JSONB)
    metadata_         = Column("metadata", JSONB, default=dict)

    events = relationship("RunEvent", back_populates="run", cascade="all, delete-orphan")


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = {"schema": "orchestrator"}

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id     = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String, nullable=False)
    payload    = Column(JSONB)
    ts         = Column(TIMESTAMP(timezone=True), default=_now)

    run = relationship("Run", back_populates="events", foreign_keys=[run_id])
