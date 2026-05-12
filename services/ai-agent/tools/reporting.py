"""
tools/reporting.py
report_finding — record an anomaly or bug with structured evidence
"""
import uuid
from datetime import datetime, timezone
from typing import Any

# In-memory findings accumulator for the session
# Persisted to DB at session close by session_manager
_session_findings: list[dict] = []


def report_finding(
    title: str,
    severity: str,
    component: str,
    description: str,
    evidence: dict | None = None,
    reproduction_steps: list[str] | None = None,
) -> dict[str, Any]:
    """
    Record a finding (bug, anomaly, unexpected behaviour) during an agent session.

    severity: critical | high | medium | low | info
    component: dispatcher | authority-claimer | graphql-server | inspect-server | anvil
    evidence: dict of supporting data (log excerpts, GraphQL responses, cast output, etc.)
    """
    finding = {
        "id":                  str(uuid.uuid4()),
        "title":               title,
        "severity":            severity,
        "component":           component,
        "description":         description,
        "evidence":            evidence or {},
        "reproduction_steps":  reproduction_steps or [],
        "reported_at":         datetime.now(tz=timezone.utc).isoformat(),
    }
    _session_findings.append(finding)
    return {
        "success": True,
        "finding_id": finding["id"],
        "total_findings": len(_session_findings),
        "message": f"Finding recorded: [{severity.upper()}] {title}",
    }


def get_all_findings() -> list[dict]:
    return list(_session_findings)


def clear_findings():
    _session_findings.clear()
