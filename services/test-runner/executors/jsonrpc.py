"""
services/test-runner/executors/jsonrpc.py
Assertion type: json_rpc

Calls Cartesi JSON-RPC API methods (cartesi_*) on the v2.x node.

API endpoint: POST http://{node_host}:{node_port}/rpc

Available methods used here:
  cartesi_listApplications()            → {data: [...], pagination: {...}}
  cartesi_listInputs("app-name")        → {data: [...], pagination: {...}}
  cartesi_listOutputs("app-name")       → {data: [...], pagination: {...}}
  cartesi_listReports("app-name")       → {data: [...], pagination: {...}}
  cartesi_listEpochs("app-name")        → {data: [...], pagination: {...}}
  cartesi_getApplication("app-name")    → {app object}

Assertion YAML:
  - type: json_rpc
    method: cartesi_listInputs        # required
    use_app_address: true             # if true, pass ctx.app_address as first param
    params: []                        # extra params appended after app identifier
    expect_count: 1                   # assert len(result.data) >= expect_count
    path: data[0].raw_data            # dotted/indexed path into result
    value: "0xdeadbeef"              # expected value at path
"""
import json
import re
import time
import logging
import httpx

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.jsonrpc")


def _resolve_path(obj, path: str):
    """Resolve a dotted/indexed path like 'data[0].raw_data' into a value."""
    for part in re.split(r"\.|(\[\d+\])", path):
        if part is None or part == "":
            continue
        if part.startswith("[") and part.endswith("]"):
            obj = obj[int(part[1:-1])]
        else:
            obj = obj[part]
    return obj


class JsonRpcExecutor(AssertionExecutor):
    assertion_type = "json_rpc"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        method        = assertion.get("method", "cartesi_listApplications")
        use_app_addr  = assertion.get("use_app_address", True)
        extra_params  = assertion.get("params", [])
        expect_count  = assertion.get("expect_count")
        path          = assertion.get("path")
        expected_val  = assertion.get("value")

        # Build params list
        params: list = []
        if use_app_addr:
            # Use app address from context — fall back to app name "app" as default
            app_id = ctx.app_address or "app"
            params.append(app_id)
        params.extend(extra_params)

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    ctx.jsonrpc_rpc_url,
                    json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                body = resp.json()

            if "error" in body:
                err = body["error"]
                # "Application not found" is a graceful case — check if we should retry
                return AssertionResult(
                    assertion_type="json_rpc",
                    passed=False,
                    detail=f"{method} error: {err.get('message', err)}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

            result = body.get("result", {})

            # Count check
            if expect_count is not None:
                data = result.get("data", [])
                actual_count = len(data)
                passed = actual_count >= expect_count
                return AssertionResult(
                    assertion_type="json_rpc",
                    passed=passed,
                    expected=f">= {expect_count} items",
                    actual=f"{actual_count} items",
                    detail=(
                        f"{method}({params[0] if params else ''}) → "
                        f"{actual_count} items (expected >= {expect_count})"
                    ),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

            # Path + value check
            if path:
                actual = _resolve_path(result, path)
                passed = actual == expected_val
                return AssertionResult(
                    assertion_type="json_rpc",
                    passed=passed,
                    expected=expected_val,
                    actual=actual,
                    detail=f"{method} path={path!r}: expected={expected_val!r} actual={actual!r}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

            # No specific check — just verify the call succeeded
            return AssertionResult(
                assertion_type="json_rpc",
                passed=True,
                detail=f"{method} succeeded",
                actual=json.dumps(result)[:200],
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        except Exception as exc:
            log.warning("json_rpc assertion error: %s", exc)
            return AssertionResult(
                assertion_type="json_rpc",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
