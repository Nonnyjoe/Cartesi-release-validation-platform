"""
services/notifier/formatters.py

Discord embed formatters for each notification event type.
All return a list[dict] that maps to the `embeds` array in a Discord webhook payload.

Discord embed colour codes (decimal):
  success  #22c55e → 2278750
  warning  #f59e0b → 16097803
  error    #ef4444 → 15680580
  info     #6366f1 → 6513393
  neutral  #64748b → 6582411
"""
from datetime import datetime, timezone
from typing import Any

COLOUR = {
    "success": 0x22C55E,
    "warning": 0xF59E0B,
    "error":   0xEF4444,
    "info":    0x6366F1,
    "neutral": 0x64748B,
}

SEVERITY_COLOUR = {
    "critical": COLOUR["error"],
    "high":     0xDC2626,
    "medium":   COLOUR["warning"],
    "low":      COLOUR["info"],
    "info":     COLOUR["neutral"],
}

DASHBOARD_URL = "http://localhost:3000"  # overridden by DASHBOARD_URL env var at runtime


def _ts(iso: str | None = None) -> str:
    if iso:
        return iso
    return datetime.now(timezone.utc).isoformat()


def _bar(value: float, total: int = 10) -> str:
    """Render a simple emoji progress bar for pass rates."""
    filled = round(value / 100 * total)
    return "█" * filled + "░" * (total - filled)


# ─── 1. Release Detected ─────────────────────────────────────────────────────

def format_release_detected(release: dict) -> list[dict]:
    tag = release.get("tag_name", "unknown")
    body = release.get("body", "") or ""
    changelog = body[:300] + ("…" if len(body) > 300 else "")
    prs = release.get("prs", [])

    fields = [
        {"name": "Tag", "value": f"`{tag}`", "inline": True},
        {"name": "Author", "value": release.get("author", "unknown"), "inline": True},
        {"name": "Auto-run", "value": "✅ Triggered", "inline": True},
    ]
    if prs:
        pr_text = "\n".join(f"• #{p['number']} {p['title']}" for p in prs[:5])
        if len(prs) > 5:
            pr_text += f"\n_…and {len(prs) - 5} more_"
        fields.append({"name": f"Merged PRs ({len(prs)})", "value": pr_text, "inline": False})

    return [{
        "title": f"🚀 New Release Detected — {tag}",
        "description": changelog or "_No changelog provided._",
        "color": COLOUR["info"],
        "fields": fields,
        "url": release.get("html_url", ""),
        "timestamp": _ts(release.get("published_at")),
        "footer": {"text": "Cartesi RVP · GitHub Watcher"},
    }]


# ─── 2. Run Queued ────────────────────────────────────────────────────────────

def format_run_queued(run: dict) -> list[dict]:
    run_id = run.get("run_id", "")
    short_id = run_id[:8]
    return [{
        "title": f"⏳ Validation Run Queued",
        "color": COLOUR["neutral"],
        "fields": [
            {"name": "Run ID",    "value": f"`{short_id}`",                  "inline": True},
            {"name": "Version",   "value": run.get("node_version", "?"),      "inline": True},
            {"name": "Priority",  "value": str(run.get("priority", 5)),       "inline": True},
            {"name": "Triggered", "value": run.get("triggered_by", "manual"), "inline": True},
        ],
        "url": f"{DASHBOARD_URL}/runs/{run_id}",
        "timestamp": _ts(run.get("created_at")),
        "footer": {"text": "Cartesi RVP · Orchestrator"},
    }]


# ─── 3. Run Completed ─────────────────────────────────────────────────────────

def format_run_completed(run: dict, report: dict | None = None) -> list[dict]:
    run_id = run.get("run_id", "")
    short_id = run_id[:8]
    pass_rate = run.get("pass_rate", 0.0) or 0.0
    passed = run.get("passed_tests", 0)
    failed = run.get("failed_tests", 0)
    total  = run.get("total_tests", 0)
    duration = run.get("duration_seconds")

    colour = COLOUR["success"] if pass_rate >= 90 else COLOUR["warning"] if pass_rate >= 70 else COLOUR["error"]
    bar = _bar(pass_rate)

    fields: list[dict] = [
        {"name": "Pass Rate",  "value": f"{bar}  **{pass_rate:.1f}%**",      "inline": False},
        {"name": "Passed",     "value": str(passed),                          "inline": True},
        {"name": "Failed",     "value": str(failed),                          "inline": True},
        {"name": "Total",      "value": str(total),                           "inline": True},
        {"name": "Version",    "value": run.get("node_version", "?"),         "inline": True},
        {"name": "Duration",   "value": f"{duration}s" if duration else "—",  "inline": True},
    ]

    # Top failing tests
    if report:
        failures = [r for r in report.get("results", []) if r.get("status") in ("failed", "error")][:5]
        if failures:
            fail_text = "\n".join(f"✗ {r['definition_name']}" for r in failures)
            fields.append({"name": "Failing Tests", "value": fail_text, "inline": False})

    return [{
        "title": f"{'✅' if pass_rate >= 90 else '⚠️' if pass_rate >= 70 else '❌'} Run Completed — {short_id}",
        "color": colour,
        "fields": fields,
        "url": f"{DASHBOARD_URL}/runs/{run_id}",
        "timestamp": _ts(run.get("completed_at")),
        "footer": {"text": "Cartesi RVP · Orchestrator"},
    }]


# ─── 4. Run Failed ────────────────────────────────────────────────────────────

def format_run_failed(run: dict) -> list[dict]:
    run_id = run.get("run_id", "")
    short_id = run_id[:8]
    error = run.get("error_message", "Unknown failure reason")[:300]

    return [{
        "title": f"❌ Run Failed — {short_id}",
        "description": f"```\n{error}\n```",
        "color": COLOUR["error"],
        "fields": [
            {"name": "Version",  "value": run.get("node_version", "?"),         "inline": True},
            {"name": "Triggered","value": run.get("triggered_by", "?"),          "inline": True},
            {"name": "Stage",    "value": run.get("status", "failed"),           "inline": True},
        ],
        "url": f"{DASHBOARD_URL}/runs/{run_id}",
        "timestamp": _ts(run.get("completed_at")),
        "footer": {"text": "Cartesi RVP · Orchestrator"},
    }]


# ─── 5. AI Finding ────────────────────────────────────────────────────────────

def format_ai_finding(finding: dict) -> list[dict]:
    severity = finding.get("severity", "info")
    evidence = finding.get("evidence", "")
    if evidence:
        evidence = evidence[:400]

    fields: list[dict] = [
        {"name": "Severity",     "value": severity.upper(),                "inline": True},
        {"name": "Session",      "value": finding.get("session_id", "?")[:8], "inline": True},
    ]
    if finding.get("recommendation"):
        fields.append({
            "name": "Recommendation",
            "value": finding["recommendation"][:200],
            "inline": False,
        })
    if evidence:
        fields.append({"name": "Evidence", "value": f"```\n{evidence}\n```", "inline": False})

    return [{
        "title": f"🔍 AI Finding — {finding.get('title', 'Unnamed')}",
        "description": finding.get("description", "")[:500],
        "color": SEVERITY_COLOUR.get(severity, COLOUR["neutral"]),
        "fields": fields,
        "timestamp": _ts(finding.get("ts")),
        "footer": {"text": "Cartesi RVP · AI Agent"},
    }]
