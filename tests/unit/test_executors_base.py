"""
tests/unit/test_executors_base.py
Unit tests for SandboxContext URL builders and AssertionResult serialisation.
Pure Python — no network or Docker calls.
"""
import sys
import os

os.environ.setdefault("SANDBOX_HOST", "testhost")
_TR = os.path.join(os.path.dirname(__file__), "../../services/test-runner")
if _TR not in sys.path:
    sys.path.insert(0, _TR)

import pytest
from executors.base import SandboxContext, AssertionResult


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_ctx(major=1, **overrides) -> SandboxContext:
    defaults = dict(
        sandbox_id   = "sbx-abc12345",
        run_id       = "run-def67890",
        anvil_port   = 28545,
        node_port    = 25000,
        graphql_port = 24000,
        docker_network = "rvp-net-test",
        node_major_version = major,
    )
    defaults.update(overrides)
    return SandboxContext(**defaults)


# ─── SandboxContext — v1.x URLs ────────────────────────────────────────────

def test_v1_graphql_url():
    assert make_ctx(1).graphql_url == "http://testhost:24000/graphql"


def test_v1_inspect_url_uses_node_port():
    # v1.x: inspect goes through node_port (HTTP API)
    assert make_ctx(1).inspect_url == "http://testhost:25000/inspect"


def test_v1_anvil_rpc_url():
    assert make_ctx(1).anvil_rpc_url == "http://testhost:28545"


# ─── SandboxContext — v2.x URLs ────────────────────────────────────────────

def test_v2_inspect_url_uses_graphql_port_slot():
    # v2.x: inspect goes through graphql_port slot (advancer at 10012)
    assert make_ctx(2).inspect_url == "http://testhost:24000/inspect"


def test_v2_jsonrpc_url():
    ctx = make_ctx(2, node_port=10011)
    assert ctx.jsonrpc_url == "http://testhost:10011"


def test_v2_jsonrpc_port_alias():
    ctx = make_ctx(2, node_port=10011)
    assert ctx.jsonrpc_port == ctx.node_port == 10011


def test_v2_inspect_port_alias():
    ctx = make_ctx(2, graphql_port=10012)
    assert ctx.inspect_port == ctx.graphql_port == 10012


# ─── app_inspect_url ──────────────────────────────────────────────────────────

def test_app_inspect_url_with_address():
    ctx = make_ctx(2, graphql_port=10012, app_address="0xDEADBEEF")
    url = ctx.app_inspect_url("status")
    assert url == "http://testhost:10012/inspect/0xDEADBEEF/status"


def test_app_inspect_url_without_address():
    ctx = make_ctx(2, graphql_port=10012)
    url = ctx.app_inspect_url("health")
    assert url == "http://testhost:10012/inspect/health"


def test_app_inspect_url_no_path():
    ctx = make_ctx(2, graphql_port=10012, app_address="0xABCD")
    # Empty path should not produce trailing slash
    url = ctx.app_inspect_url("")
    assert not url.endswith("/")


def test_app_jsonrpc_url():
    ctx = make_ctx(2, node_port=10011)
    assert ctx.app_jsonrpc_url() == "http://testhost:10011"


# ─── AssertionResult ──────────────────────────────────────────────────────────

def test_assertion_result_to_dict_passed():
    r = AssertionResult(
        assertion_type = "http_status",
        passed         = True,
        expected       = 200,
        actual         = 200,
        detail         = "GET /healthz → 200",
        duration_ms    = 42,
    )
    d = r.to_dict()
    assert d["assertion_type"] == "http_status"
    assert d["passed"]         is True
    assert d["expected"]       == 200
    assert d["actual"]         == 200
    assert d["detail"]         == "GET /healthz → 200"
    assert d["duration_ms"]    == 42


def test_assertion_result_to_dict_failed():
    r = AssertionResult(
        assertion_type = "graphql",
        passed         = False,
        expected       = "foo",
        actual         = "bar",
        detail         = "Path 'a.b': expected='foo' actual='bar'",
    )
    d = r.to_dict()
    assert d["passed"] is False
    assert d["expected"] == "foo"
    assert d["actual"]   == "bar"


def test_assertion_result_defaults_are_none():
    r = AssertionResult(assertion_type="chain_tx", passed=True)
    d = r.to_dict()
    assert d["expected"]    is None
    assert d["actual"]      is None
    assert d["detail"]      is None
    assert d["duration_ms"] is None


def test_assertion_result_to_dict_has_all_keys():
    r = AssertionResult(assertion_type="voucher", passed=False)
    keys = set(r.to_dict().keys())
    assert keys == {"assertion_type", "passed", "expected", "actual", "detail", "duration_ms"}
