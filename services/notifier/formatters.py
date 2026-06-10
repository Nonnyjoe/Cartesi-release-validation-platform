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
import re
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


def _phase_number(phase: str) -> int:
    """Extract leading integer from 'Phase N: ...' strings for sorting."""
    m = re.match(r"Phase\s+(\d+)", phase or "")
    return int(m.group(1)) if m else 9999


def _phase_icon(pass_rate: float) -> str:
    if pass_rate >= 100:
        return "✅"
    if pass_rate >= 80:
        return "⚠️"
    return "❌"


def _phase_colour_text(pass_rate: float) -> str:
    """ANSI-style label for inline display."""
    if pass_rate >= 100:
        return "PASS"
    if pass_rate > 0:
        return "PARTIAL"
    return "FAIL"


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
        "title": "⏳ Validation Run Queued",
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


# ─── helpers shared by completed / warning formatters ────────────────────────

def _build_phase_lines(phases: list[dict]) -> str:
    """
    Build a compact phase summary block for the embed description.
    Each line: <icon> Phase N: Name   X/Y  (rate%)
    """
    sorted_phases = sorted(phases, key=lambda p: _phase_number(p.get("phase", "")))
    lines = []
    for ph in sorted_phases:
        icon     = _phase_icon(ph["pass_rate"])
        name     = ph.get("phase") or "Uncategorised"
        passed   = ph.get("passed", 0)
        total    = ph.get("total", 0)
        rate     = ph.get("pass_rate", 0.0)
        bar      = _bar(rate, total=8)
        lines.append(f"{icon} **{name}**  `{passed}/{total}`  {bar}  **{rate:.0f}%**")
    return "\n".join(lines)


# ─── 3. Run Completed (all tests passed ≥ threshold) ─────────────────────────

def format_run_completed(run: dict, report: dict | None = None) -> list[dict]:
    run_id   = run.get("run_id", "")
    short_id = run_id[:8]
    pass_rate  = float(run.get("pass_rate", 0.0) or 0.0)
    passed     = run.get("passed_tests", 0) or 0
    failed     = run.get("failed_tests", 0) or 0
    total      = run.get("total_tests", 0) or 0
    duration   = run.get("duration_seconds")
    release    = run.get("release_tag", "—")
    triggered  = run.get("triggered_by", "—")
    triggered_user = run.get("triggered_by_user")
    phases: list[dict] = run.get("phases") or []
    top_failures: list[dict] = run.get("top_failures") or []

    by_str = f"{triggered_user} ({triggered})" if triggered_user else triggered

    # Header bar
    bar = _bar(pass_rate)

    # Build description: overall bar + phase breakdown
    desc_parts = [
        f"## {bar}  **{pass_rate:.1f}%** pass rate\n",
    ]
    if phases:
        desc_parts.append(_build_phase_lines(phases))

    description = "\n".join(desc_parts)

    fields: list[dict] = [
        {"name": "Release",   "value": f"`{release}`",                         "inline": True},
        {"name": "Triggered", "value": by_str,                                 "inline": True},
        {"name": "Duration",  "value": f"{duration}s" if duration else "—",    "inline": True},
        {"name": "✅ Passed",  "value": str(passed),                            "inline": True},
        {"name": "❌ Failed",  "value": str(failed),                            "inline": True},
        {"name": "Total",     "value": str(total),                              "inline": True},
    ]

    # Append failing test details if any slipped through (warning threshold)
    if top_failures:
        fail_lines = []
        for t in top_failures[:5]:
            status_icon = "⚠️" if t.get("status") == "error" else "✗"
            error_snippet = t.get("error", "").strip()
            if error_snippet:
                fail_lines.append(f"{status_icon} **{t['name']}**\n  `{error_snippet[:120]}`")
            else:
                fail_lines.append(f"{status_icon} **{t['name']}** — _{t.get('status', 'failed')}_")
        fields.append({"name": "Failing Tests", "value": "\n".join(fail_lines), "inline": False})

    # Colour and title based on pass rate
    if pass_rate >= 100:
        colour = COLOUR["success"]
        title  = f"✅ All Tests Passed — {short_id}"
    elif pass_rate >= 80:
        colour = COLOUR["warning"]
        title  = f"⚠️ Run Completed with Warnings — {short_id}"
    else:
        colour = COLOUR["error"]
        title  = f"❌ Run Completed — Low Pass Rate — {short_id}"

    return [{
        "title":       title,
        "description": description,
        "color":       colour,
        "fields":      fields,
        "url":         f"{DASHBOARD_URL}/runs/{run_id}",
        "timestamp":   _ts(),
        "footer":      {"text": "Cartesi RVP · Orchestrator"},
    }]


# ─── 4. Run Failed (infrastructure / provisioning failure) ───────────────────

def format_run_failed(run: dict) -> list[dict]:
    run_id   = run.get("run_id", "")
    short_id = run_id[:8]
    release  = run.get("release_tag", "—")
    triggered = run.get("triggered_by", "—")
    triggered_user = run.get("triggered_by_user")
    duration = run.get("duration_seconds")
    by_str   = f"{triggered_user} ({triggered})" if triggered_user else triggered

    # Determine failure stage and reason
    stage   = run.get("status", "failed")
    error   = (run.get("error_message") or run.get("fields", {}).get("error_message") or "Unknown failure reason")
    error   = error.strip()[:400]

    # Phase results up to the point of failure (may be partial)
    phases: list[dict] = run.get("phases") or []
    top_failures: list[dict] = run.get("top_failures") or []

    # Build description
    desc_parts = ["### Failure Reason\n```\n" + error + "\n```"]
    if phases:
        desc_parts.append("\n### Phase Results at Time of Failure")
        desc_parts.append(_build_phase_lines(phases))

    description = "\n".join(desc_parts)

    fields: list[dict] = [
        {"name": "Release",   "value": f"`{release}`",                      "inline": True},
        {"name": "Triggered", "value": by_str,                              "inline": True},
        {"name": "Stage",     "value": stage.upper(),                       "inline": True},
        {"name": "Duration",  "value": f"{duration}s" if duration else "—", "inline": True},
    ]

    if top_failures:
        fail_lines = []
        for t in top_failures[:5]:
            err = t.get("error", "").strip()
            if err:
                fail_lines.append(f"✗ **{t['name']}**\n  `{err[:120]}`")
            else:
                fail_lines.append(f"✗ **{t['name']}** — _{t.get('status', 'failed')}_")
        fields.append({"name": "Failing Tests", "value": "\n".join(fail_lines), "inline": False})

    return [{
        "title":       f"❌ Run Failed — {short_id}",
        "description": description,
        "color":       COLOUR["error"],
        "fields":      fields,
        "url":         f"{DASHBOARD_URL}/runs/{run_id}",
        "timestamp":   _ts(),
        "footer":      {"text": "Cartesi RVP · Orchestrator"},
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
