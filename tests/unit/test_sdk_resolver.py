"""
tests/unit/test_sdk_resolver.py
Unit tests for pure helper functions in shared/sdk_resolver.py.
No network calls — only local string parsing and static lookups.
"""
import sys
import os

_SHARED = os.path.join(os.path.dirname(__file__), "../../shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import pytest
from sdk_resolver import (
    node_major_version,
    derive_image_tag,
    extract_versions_from_cli_body,
    _extract_sdk_from_body,
)


# ─── node_major_version ───────────────────────────────────────────────────────

@pytest.mark.parametrize("tag,expected", [
    ("v1.5.1",          1),
    ("1.5.1",           1),
    ("v2.0.0-alpha.11", 2),
    ("2.0.0-alpha.11",  2),
    ("v3.1.0",          3),
    ("v10.0.0",         10),
    ("v1.0.0",          1),
])
def test_node_major_version_valid_tags(tag, expected):
    assert node_major_version(tag) == expected


@pytest.mark.parametrize("tag", ["not-a-version", "", "abc"])
def test_node_major_version_invalid_falls_back_to_1(tag):
    assert node_major_version(tag) == 1


# ─── derive_image_tag ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("node_tag,sdk,expected", [
    ("v1.5.1",          None,                "cartesi/rollups-node:1.5.1"),
    ("1.5.1",           None,                "cartesi/rollups-node:1.5.1"),
    ("v1.4.0",          "some-sdk",          "cartesi/rollups-node:1.4.0"),   # v1.x ignores sdk
    ("v2.0.0-alpha.11", "0.12.0-alpha.39",   "cartesi/rollups-runtime:0.12.0-alpha.39"),
    # v2 without known sdk falls back to rollups-node image
    ("v2.0.0-alpha.11", None,                "cartesi/rollups-node:2.0.0-alpha.11"),
])
def test_derive_image_tag(node_tag, sdk, expected):
    assert derive_image_tag(node_tag, sdk) == expected


def test_derive_image_tag_strips_v_prefix():
    assert derive_image_tag("v1.5.1", None) == "cartesi/rollups-node:1.5.1"
    # No 'v' in the image tag
    assert not derive_image_tag("v1.5.1", None).startswith("cartesi/rollups-node:v")


# ─── _extract_sdk_from_body ───────────────────────────────────────────────────

@pytest.mark.parametrize("body,expected", [
    # @cartesi/sdk pattern
    ("Bump @cartesi/sdk@ 0.12.0-alpha.39 support",              "0.12.0-alpha.39"),
    # rollups-runtime image pattern
    ("Use cartesi/rollups-runtime:0.12.0-alpha.39 for release",  "0.12.0-alpha.39"),
    # rollups-database image pattern
    ("Use cartesi/rollups-database:0.11.0-alpha.5 as DB",        "0.11.0-alpha.5"),
    # case-insensitive
    ("CARTESI/ROLLUPS-RUNTIME:1.2.3",                            "1.2.3"),
    # nothing present
    ("No SDK version mentioned here",                            None),
])
def test_extract_sdk_from_body(body, expected):
    assert _extract_sdk_from_body(body) == expected


# ─── extract_versions_from_cli_body ───────────────────────────────────────────

def test_extract_versions_full_body():
    body = """\
Release v2.0.0-alpha.34 of @cartesi/cli

- Bump rollups-node to v2.0.0-alpha.11
- Uses @cartesi/sdk@ 0.12.0-alpha.39
- Uses @cartesi/devnet@ 0.2.0-alpha.5
- Uses @cartesi/rollups-contracts@ 2.0.0-alpha.1
"""
    sdk, devnet, contracts, node = extract_versions_from_cli_body(body)
    assert sdk       == "0.12.0-alpha.39"
    assert devnet    == "0.2.0-alpha.5"
    assert contracts == "2.0.0-alpha.1"
    assert node      == "2.0.0-alpha.11"


def test_extract_versions_empty_body():
    sdk, devnet, contracts, node = extract_versions_from_cli_body("")
    assert sdk is None and devnet is None and contracts is None and node is None


def test_extract_versions_only_node_bump():
    body = "Bump rollups-node to v1.5.1 — no SDK info here"
    sdk, devnet, contracts, node = extract_versions_from_cli_body(body)
    assert sdk  is None
    assert node == "1.5.1"


def test_extract_versions_runtime_image_pattern():
    body = "cartesi/rollups-runtime:0.12.0-alpha.39 image update"
    sdk, devnet, contracts, node = extract_versions_from_cli_body(body)
    assert sdk == "0.12.0-alpha.39"


def test_extract_versions_returns_tuple_of_four():
    result = extract_versions_from_cli_body("anything")
    assert len(result) == 4


def test_extract_versions_no_v_prefix_in_returned_strings():
    body = "Bump rollups-node to v2.0.0-alpha.11"
    _, _, _, node = extract_versions_from_cli_body(body)
    # Returned version strings should not have leading 'v'
    assert node is not None
    assert not node.startswith("v"), f"Expected no 'v' prefix, got {node!r}"
