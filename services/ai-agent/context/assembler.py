"""
services/ai-agent/context/assembler.py
Builds the Claude system prompt by layering:
  1. Operator persona + rules (in the mode template)
  2. Project knowledge — sources/project/*.md, including the auto-generated test catalog
  3. Cartesi Skills summary — "When to use" + first heading of each key skill
  4. Mode-specific framing + release context

Full Cartesi Skills (~4400 lines) are reachable on demand via the `lookup_skill` tool.
"""
import json
from pathlib import Path

SOURCES_DIR    = Path(__file__).parent / "sources"
PROJECT_DIR    = SOURCES_DIR / "project"
TEMPLATES_DIR  = Path(__file__).parent / "templates"
SKILLS_DIR     = Path("/app/knowledge/cartesi-skills")

# Skills surfaced in the system prompt (summaries only).
# Full text is fetched on demand via the lookup_skill tool.
SKILLS_FOR_SUMMARY = [
    "cartesi-l1-contracts",
    "cartesi-jsonrpc",
    "cartesi-local-dev",
    "cartesi-debug",
]

# Order matters: project knowledge is read top-down, included in the system prompt.
PROJECT_FILES = [
    "executor-reference.md",
    "test-catalog.md",
    "sandbox-topology.md",
    "contracts-devnet.md",
    "cartesi-jsonrpc-quickref.md",
    "test-app-behavior.md",
]


def _read(filename: str) -> str:
    return (SOURCES_DIR / filename).read_text()


def _read_project(filename: str) -> str:
    p = PROJECT_DIR / filename
    if not p.exists():
        return f"<!-- {filename} not generated yet -->"
    return p.read_text()


def _read_skill_summary(skill_name: str) -> str:
    """Pull the top of a skill's SKILL.md — first ~150 lines, enough for the "When to use" +
    first H2 block. Returns a fallback if the file isn't mounted."""
    p = SKILLS_DIR / skill_name / "SKILL.md"
    if not p.exists():
        return f"### {skill_name}\n_(skill not mounted at /app/knowledge/cartesi-skills)_\n"
    lines = p.read_text().splitlines()
    out: list[str] = []
    seen_first_h2 = False
    for line in lines[:200]:
        if line.startswith("## "):
            if seen_first_h2:
                break
            seen_first_h2 = True
        out.append(line)
    return "\n".join(out).rstrip() + "\n"


def assemble_project_knowledge() -> str:
    parts = [
        "<!-- PROJECT KNOWLEDGE — specific to this test-suite codebase and the sandbox environment -->",
    ]
    for name in PROJECT_FILES:
        parts.append(f"\n---\n\n<!-- file: {name} -->\n")
        parts.append(_read_project(name))
    return "\n".join(parts)


def assemble_skills_summary() -> str:
    parts = [
        "<!-- CARTESI SKILLS — public Cartesi knowledge. Use `lookup_skill` to read full sections. -->",
    ]
    for name in SKILLS_FOR_SUMMARY:
        parts.append(f"\n---\n\n<!-- skill: {name} -->\n")
        parts.append(_read_skill_summary(name))
    parts.append(
        "\n---\n\n"
        "Available skills (use `lookup_skill(skill_name=..., section=...)` for full content):\n"
        "- cartesi-scaffold\n"
        "- cartesi-backend-core\n"
        "- cartesi-python-backend\n"
        "- cartesi-js-backend\n"
        "- cartesi-frontend\n"
        "- cartesi-l1-contracts\n"
        "- cartesi-jsonrpc\n"
        "- cartesi-local-dev\n"
        "- cartesi-deploy\n"
        "- cartesi-debug\n",
    )
    return "\n".join(parts)


def format_release_context(release_tag: str, changelog: str | None, pr_summaries: list[str]) -> str:
    parts = [f"## Current Release Under Test: {release_tag}"]
    if changelog:
        parts.append(f"\n### Changelog\n{changelog}")
    if pr_summaries:
        parts.append("\n### PR Summaries")
        for i, summary in enumerate(pr_summaries, 1):
            parts.append(f"\n**PR {i}:** {summary}")
    return "\n".join(parts)


def build_system_prompt(
    mode: str,
    release_tag: str,
    pr_summaries: list[str] | None = None,
    changelog: str | None = None,
    goal: str | None = None,
    base_test_slug: str | None = None,
    sandbox_id: str | None = None,
) -> str:
    """Assemble the full system prompt for a Claude AI session.

    Layered context (~25–30k tokens):
      - Legacy architecture/GraphQL/inspect/component-map blocks (kept for backward compat)
      - Project knowledge bundle (executor reference, test catalog, topology, contracts, etc.)
      - Cartesi Skills summary (full text via lookup_skill tool)
      - Release context (tag, changelog, PR summaries)

    Remaining headroom: ~170k tokens for conversation + tool calls.
    """
    architecture       = _read("architecture.md")
    graphql_schema     = _read("graphql_schema.graphql")
    inspect_api        = _read("inspect_api.yaml")
    component_map      = json.dumps(json.loads(_read("component_map.json")), indent=2)
    project_knowledge  = assemble_project_knowledge()
    skills_summary     = assemble_skills_summary()
    release_ctx        = format_release_context(
        release_tag, changelog, pr_summaries or [],
    )

    # Load the mode-specific prompt template
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"template_{mode}",
        TEMPLATES_DIR / f"{mode}.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    return mod.render(
        architecture=architecture,
        graphql_schema=graphql_schema,
        inspect_api=inspect_api,
        component_map=component_map,
        project_knowledge=project_knowledge,
        skills_summary=skills_summary,
        release_context=release_ctx,
        goal=goal,
        base_test_slug=base_test_slug,
        sandbox_id=sandbox_id,
    )
