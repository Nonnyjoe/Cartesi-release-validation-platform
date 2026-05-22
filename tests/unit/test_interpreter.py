"""
tests/unit/test_interpreter.py
Unit tests for the YAML-frontmatter + Markdown body parser.
No external dependencies beyond pyyaml.
"""
import sys
import os

_TR = os.path.join(os.path.dirname(__file__), "../../services/test-runner")
if _TR not in sys.path:
    sys.path.insert(0, _TR)

import pytest
from interpreter import parse_definition


# ─── Fixtures ─────────────────────────────────────────────────────────────────

VALID_DOC = """\
---
id: basic-test
name: Basic Test
assertions:
  - type: http_status
    endpoint: /healthz
    expect: 200
---

## Description

This is a basic health-check test.
"""

MULTI_ASSERT_DOC = """\
---
id: multi-assert
name: Multi Assertion Test
version: 2
tags: [smoke, core]
timeout_seconds: 60
assertions:
  - type: http_status
    endpoint: /healthz
    expect: 200
  - type: graphql
    query: "{ inputs { edges { node { index } } } }"
    expect:
      path: inputs.edges
      value: []
  - type: log_contains
    component: node
    pattern: "ready"
---

Body text here.
"""


# ─── Happy path ───────────────────────────────────────────────────────────────

def test_parse_valid_definition_required_fields():
    result = parse_definition(VALID_DOC)
    assert result["id"]   == "basic-test"
    assert result["name"] == "Basic Test"
    assert len(result["assertions"]) == 1
    assert result["assertions"][0]["type"] == "http_status"


def test_parse_sets_defaults():
    result = parse_definition(VALID_DOC)
    assert result["timeout_seconds"] == 120
    assert result["tags"]            == []
    assert result["inputs"]          == {}
    assert result["requires"]        == []
    assert result["version"]         == 1


def test_parse_body_stripped():
    result = parse_definition(VALID_DOC)
    assert result["body"] == "## Description\n\nThis is a basic health-check test."


def test_parse_multiple_assertions():
    result = parse_definition(MULTI_ASSERT_DOC)
    assert len(result["assertions"]) == 3
    assert result["assertions"][0]["type"] == "http_status"
    assert result["assertions"][1]["type"] == "graphql"
    assert result["assertions"][2]["type"] == "log_contains"


def test_parse_explicit_version():
    result = parse_definition(MULTI_ASSERT_DOC)
    assert result["version"] == 2


def test_parse_explicit_tags():
    result = parse_definition(MULTI_ASSERT_DOC)
    assert result["tags"] == ["smoke", "core"]


def test_parse_explicit_timeout():
    result = parse_definition(MULTI_ASSERT_DOC)
    assert result["timeout_seconds"] == 60


def test_parse_body_content():
    result = parse_definition(MULTI_ASSERT_DOC)
    assert "Body text here." in result["body"]


def test_parse_empty_body():
    """A definition with no body text (just frontmatter + trailing newline)."""
    doc = """\
---
id: no-body
name: No Body Test
assertions: []
---
"""
    result = parse_definition(doc)
    assert result["body"] == ""


def test_parse_definition_no_trailing_newline():
    """
    Frontmatter closed by --- without a trailing \\n (e.g. programmatically
    generated definitions).  After the bug-fix the regex accepts \\n or EOF.
    """
    doc = "---\nid: eof-test\nname: EOF Test\nassertions: []\n---"
    result = parse_definition(doc)
    assert result["id"] == "eof-test"


# ─── Missing required fields ──────────────────────────────────────────────────

def test_parse_missing_id_raises():
    doc = "---\nname: No ID\nassertions: []\n---\n"
    with pytest.raises(ValueError, match="Missing required frontmatter field: 'id'"):
        parse_definition(doc)


def test_parse_missing_name_raises():
    doc = "---\nid: no-name\nassertions: []\n---\n"
    with pytest.raises(ValueError, match="Missing required frontmatter field: 'name'"):
        parse_definition(doc)


def test_parse_missing_assertions_raises():
    doc = "---\nid: no-assertions\nname: No Assertions\n---\n"
    with pytest.raises(ValueError, match="Missing required frontmatter field: 'assertions'"):
        parse_definition(doc)


# ─── Malformed input ──────────────────────────────────────────────────────────

def test_parse_invalid_yaml_raises():
    doc = "---\nid: bad\nname: {broken: yaml:\n---\n"
    with pytest.raises(ValueError, match="Invalid YAML frontmatter"):
        parse_definition(doc)


def test_parse_no_frontmatter_raises():
    with pytest.raises(ValueError, match="Definition must start with YAML frontmatter"):
        parse_definition("Plain text, no frontmatter.")


def test_parse_frontmatter_is_list_raises():
    """YAML frontmatter that is a list (not a mapping) must be rejected."""
    doc = "---\n- item1\n- item2\n---\n"
    with pytest.raises(ValueError, match="YAML frontmatter must be a mapping"):
        parse_definition(doc)


def test_parse_empty_string_raises():
    with pytest.raises(ValueError, match="Definition must start with YAML frontmatter"):
        parse_definition("")
