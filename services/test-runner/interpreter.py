"""
services/test-runner/interpreter.py
Parses a YAML-frontmatter + Markdown body definition document.
Returns a structured dict the executor can work with.
"""
import re
import logging
from typing import Any

import yaml

log = logging.getLogger("test-runner.interpreter")

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_definition(raw: str) -> dict[str, Any]:
    """
    Parse a YAML frontmatter + Markdown body document.
    Returns a dict with all frontmatter fields plus 'body' (the markdown text).
    Raises ValueError on malformed input.
    """
    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError("Definition must start with YAML frontmatter (---...---)")

    yaml_text = match.group(1)
    body      = raw[match.end():]

    try:
        meta = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML frontmatter: {exc}") from exc

    if not isinstance(meta, dict):
        raise ValueError("YAML frontmatter must be a mapping")

    # Validate required fields
    for required in ("id", "name", "assertions"):
        if required not in meta:
            raise ValueError(f"Missing required frontmatter field: '{required}'")

    meta["body"] = body.strip()
    meta.setdefault("timeout_seconds", 120)
    meta.setdefault("tags", [])
    meta.setdefault("inputs", {})
    meta.setdefault("requires", [])
    meta.setdefault("version", 1)

    return meta
