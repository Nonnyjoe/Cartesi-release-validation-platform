"""
services/ai-agent/context/assembler.py
Builds the Claude system prompt by injecting Cartesi docs directly into context.
No RAG needed — Claude's 200k window fits everything comfortably (~10k tokens total).
"""
import json
from pathlib import Path

SOURCES_DIR = Path(__file__).parent / "sources"
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _read(filename: str) -> str:
    return (SOURCES_DIR / filename).read_text()


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
    """
    Assembles the full system prompt for a Claude AI session.

    Injected context (~10k tokens):
      - Cartesi architecture reference
      - GraphQL schema
      - Inspect API spec
      - Component map (container names, log keywords, contract addresses)
      - Release context (tag, changelog, PR summaries)

    Remaining headroom: ~190k tokens for conversation + tool calls.
    """
    architecture  = _read("architecture.md")
    graphql_schema = _read("graphql_schema.graphql")
    inspect_api   = _read("inspect_api.yaml")
    component_map = json.dumps(json.loads(_read("component_map.json")), indent=2)
    release_ctx   = format_release_context(
        release_tag, changelog, pr_summaries or []
    )

    # Load the mode-specific prompt template
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        f"template_{mode}",
        TEMPLATES_DIR / f"{mode}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    return mod.render(
        architecture=architecture,
        graphql_schema=graphql_schema,
        inspect_api=inspect_api,
        component_map=component_map,
        release_context=release_ctx,
        goal=goal,
        base_test_slug=base_test_slug,
        sandbox_id=sandbox_id,
    )
