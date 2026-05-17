"""
services/orchestrator/api/routes/reports.py
GET /reports/{run_id} — compiled test report for a run
"""
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db

router = APIRouter()


class ReportResponse(BaseModel):
    run_id:     str
    release_tag: str
    status:     str
    pass_rate:  Optional[float]
    total:      int
    passed:     int
    failed:     int
    error:      int
    results:    List[Dict[str, Any]]


@router.get("/{run_id}", response_model=ReportResponse)
async def get_report(run_id: str, db: AsyncSession = Depends(get_db)):
    # Fetch run
    run_row = await db.execute(
        text("SELECT id, release_tag, status, pass_rate, report "
             "FROM orchestrator.runs WHERE id = :id"),
        {"id": run_id},
    )
    run = run_row.fetchone()
    if not run:
        raise HTTPException(404, detail=f"Run {run_id} not found")

    # Fetch test results for this run (cross-schema read)
    results_rows = await db.execute(
        text("""
            SELECT r.id, r.definition_id, r.status, r.duration_ms,
                   r.assertion_results, r.error_message, r.started_at, r.completed_at,
                   d.slug as test_slug, d.name as test_name
            FROM tests.results r
            JOIN tests.definitions d ON d.id = r.definition_id
            WHERE r.run_id = :run_id
            ORDER BY r.started_at
        """),
        {"run_id": run_id},
    )

    def _result_row(row) -> dict:
        return {
            "id":                str(row.id),
            "definition_id":     str(row.definition_id),
            "test_slug":         row.test_slug,
            "test_name":         row.test_name,
            "status":            row.status,
            "duration_ms":       row.duration_ms,
            "assertion_results": row.assertion_results or [],
            "error_message":     row.error_message,
            "started_at":        row.started_at.isoformat() if row.started_at else None,
            "completed_at":      row.completed_at.isoformat() if row.completed_at else None,
        }

    results = [_result_row(r) for r in results_rows]

    statuses = [r["status"] for r in results]
    total  = len(results)
    passed = statuses.count("passed")
    failed = statuses.count("failed")
    error  = statuses.count("error") + statuses.count("timeout")

    return {
        "run_id":      str(run.id),
        "release_tag": run.release_tag,
        "status":      run.status,
        "pass_rate":   float(run.pass_rate) if run.pass_rate else None,
        "total":       total,
        "passed":      passed,
        "failed":      failed,
        "error":       error,
        "results":     results,
    }
