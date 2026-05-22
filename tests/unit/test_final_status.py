"""
tests/unit/test_final_status.py
Unit tests for _final_status() in orchestrator's test_results consumer.

The function maps a pass-rate float to one of three terminal run statuses:
  100%+          → "completed"
  80–99.9%       → "warning"
  below 80%      → "failed"

Thresholds are controlled by env vars:
  PASS_THRESHOLD_COMPLETED  (default 100.0)
  PASS_THRESHOLD_WARNING    (default 80.0)
"""
import sys
import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("RABBITMQ_URL", "amqp://rvp:test@localhost:5672/")

_ORCH = os.path.join(os.path.dirname(__file__), "../../services/orchestrator")
if _ORCH not in sys.path:
    sys.path.insert(0, _ORCH)

import pytest
from consumers.test_results import _final_status


# ─── Default thresholds (100.0 / 80.0) ───────────────────────────────────────

def test_100_percent_is_completed():
    assert _final_status(100.0) == "completed"


def test_above_100_is_still_completed():
    # Should never happen in practice but must be safe
    assert _final_status(100.1) == "completed"


def test_exactly_80_is_warning():
    # 80.0 >= WARNING threshold (80.0) but < COMPLETED threshold (100.0)
    assert _final_status(80.0) == "warning"


def test_between_80_and_100_is_warning():
    for rate in (80.1, 85.0, 90.0, 95.5, 99.9):
        assert _final_status(rate) == "warning", f"Expected 'warning' for {rate}"


def test_79_9_is_failed():
    assert _final_status(79.9) == "failed"


def test_0_percent_is_failed():
    assert _final_status(0.0) == "failed"


def test_50_percent_is_failed():
    assert _final_status(50.0) == "failed"


# ─── Threshold boundary correctness ──────────────────────────────────────────

def test_warning_lower_bound_is_inclusive():
    """_final_status(80.0) must be 'warning', not 'failed'."""
    assert _final_status(80.0) != "failed"


def test_completed_lower_bound_is_inclusive():
    """_final_status(100.0) must be 'completed', not 'warning'."""
    assert _final_status(100.0) != "warning"


def test_return_type_is_string():
    for rate in (0.0, 80.0, 100.0):
        assert isinstance(_final_status(rate), str)
