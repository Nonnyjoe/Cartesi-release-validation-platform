"""Lazy access to the full Cartesi Skills knowledge base.

The system prompt includes a summary of each skill. The full text (each SKILL.md is hundreds of
lines) is reachable on demand via this tool, keyed by skill name and optional section heading.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("ai-agent.skill_lookup")

SKILLS_ROOT = Path("/app/knowledge/cartesi-skills")

VALID_SKILLS = {
    "cartesi-scaffold",
    "cartesi-backend-core",
    "cartesi-python-backend",
    "cartesi-js-backend",
    "cartesi-frontend",
    "cartesi-l1-contracts",
    "cartesi-jsonrpc",
    "cartesi-local-dev",
    "cartesi-deploy",
    "cartesi-debug",
}

MAX_SECTION_BYTES = 8_000


def _list_sections(text: str) -> list[str]:
    return [ln[3:].strip() for ln in text.splitlines() if ln.startswith("## ")]


def _extract_section(text: str, section: str) -> str | None:
    """Return the markdown for a single H2 section, or None if not found."""
    lines = text.splitlines()
    needle = section.strip().lower()
    out: list[str] = []
    capturing = False
    for ln in lines:
        if ln.startswith("## "):
            heading = ln[3:].strip().lower()
            if heading == needle:
                capturing = True
                out.append(ln)
                continue
            if capturing:
                break
        elif capturing:
            out.append(ln)
    if not out:
        return None
    return "\n".join(out).rstrip()


def lookup_skill(skill_name: str, section: str | None = None) -> dict:
    if skill_name not in VALID_SKILLS:
        return {
            "success": False,
            "error": f"Unknown skill {skill_name!r}",
            "available": sorted(VALID_SKILLS),
        }

    p = SKILLS_ROOT / skill_name / "SKILL.md"
    if not p.exists():
        return {
            "success": False,
            "error": f"Skill file not mounted: {p}",
        }

    text = p.read_text()

    if section is None:
        # Return the table of contents (H2 headings)
        sections = _list_sections(text)
        return {
            "success": True,
            "skill": skill_name,
            "sections": sections,
            "hint": "Call again with `section=<heading>` to read a specific section.",
        }

    body = _extract_section(text, section)
    if body is None:
        sections = _list_sections(text)
        return {
            "success": False,
            "error": f"Section {section!r} not found in {skill_name}",
            "available_sections": sections,
        }

    if len(body) > MAX_SECTION_BYTES:
        body = body[:MAX_SECTION_BYTES] + "\n\n[... truncated; section larger than limit]"

    return {
        "success": True,
        "skill": skill_name,
        "section": section,
        "content": body,
    }
