"""
services/test-runner/executors/jsonrpc.py
Assertion type: json_rpc

Calls Cartesi JSON-RPC API methods (cartesi_*) on the v2.x node.

API endpoint: POST http://{node_host}:{node_port}/rpc

Assertion YAML:
  - type: json_rpc
    method: cartesi_listInputs        # required
    use_app_address: true             # if true, pass ctx.app_address as first param
    params: []                        # extra params appended after app identifier
    expect_count: 1                   # assert len(result.data) >= expect_count
    expect_count_exact: 3             # assert len(result.data) == exact value
    path: data[0].raw_data            # dotted/indexed path into result
    value: "0xdeadbeef"              # expected value at path
    expect_error: true                # assert response contains error field
    expect_error_code: -32601         # assert error.code == value
    raw_body: "not json"             # send raw string as body (for parse-error tests)
    stress_count: 50                  # repeat the request N times, assert all succeed
    pagination_limit: 10              # send as named param "limit" (requires named params mode)
    pagination_offset: 5              # send as named param "offset" (requires named params mode)
    expect_has_field: "data"         # assert result contains this field
    use_last_epoch: true             # fetch last accepted epoch index and use as epoch_index param
"""
import asyncio
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
        method             = assertion.get("method", "cartesi_listApplications")
        use_app_addr       = assertion.get("use_app_address", True)
        extra_params       = assertion.get("params", [])
        expect_count       = assertion.get("expect_count")
        expect_count_exact = assertion.get("expect_count_exact")
        path               = assertion.get("path")
        expected_val       = assertion.get("value")
        expect_error       = assertion.get("expect_error", False)
        expect_error_code  = assertion.get("expect_error_code")
        raw_body           = assertion.get("raw_body")
        stress_count       = assertion.get("stress_count")
        pagination_limit   = assertion.get("pagination_limit")
        pagination_offset  = assertion.get("pagination_offset")
        expect_has_field   = assertion.get("expect_has_field")
        use_last_epoch     = assertion.get("use_last_epoch", False)

        app_id = (ctx.app_address or "app") if use_app_addr else None

        # Pagination uses named params (the v2 API requires individual named fields,
        # not a nested pagination object).
        if pagination_limit is not None or pagination_offset is not None:
            params: dict = {}
            if app_id:
                params["application"] = app_id
            if pagination_limit is not None:
                params["limit"] = pagination_limit
            if pagination_offset is not None:
                params["offset"] = pagination_offset
        else:
            # Positional params
            params: list = []
            if app_id:
                params.append(app_id)
            params.extend(extra_params)

        t0 = time.monotonic()
        url = ctx.jsonrpc_rpc_url

        # use_last_epoch: first fetch the last accepted epoch index, then inject it
        # into params as the epoch_index parameter (hex string format required).
        if use_last_epoch and app_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.post(url, json={
                        "jsonrpc": "2.0",
                        "method": "cartesi_getLastAcceptedEpochIndex",
                        "params": [app_id],
                        "id": 99,
                    }, headers={"Content-Type": "application/json"})
                    epoch_resp = r.json()
                    epoch_idx = epoch_resp.get("result", {}).get("data")
                    if epoch_idx:
                        if isinstance(params, list):
                            params.append(epoch_idx)
                        else:
                            params["epoch_index"] = epoch_idx
            except Exception as exc:
                log.warning("use_last_epoch fetch failed: %s", exc)

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                # Stress test: fire N concurrent requests
                if stress_count:
                    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
                    tasks = [
                        client.post(url, json=payload, headers={"Content-Type": "application/json"})
                        for _ in range(stress_count)
                    ]
                    responses = await asyncio.gather(*tasks, return_exceptions=True)
                    errors = [r for r in responses if isinstance(r, Exception)]
                    non_200 = [r for r in responses if not isinstance(r, Exception) and r.status_code >= 400]
                    passed = len(errors) == 0 and len(non_200) == 0
                    return AssertionResult(
                        assertion_type="json_rpc",
                        passed=passed,
                        detail=(
                            f"{method} × {stress_count}: "
                            f"{len(errors)} exceptions, {len(non_200)} HTTP errors"
                        ),
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )

                # Raw body (for parse-error / batch tests)
                if raw_body is not None:
                    resp = await client.post(
                        url,
                        content=raw_body.encode() if isinstance(raw_body, str) else raw_body,
                        headers={"Content-Type": "application/json"},
                    )
                    # HTTP 4xx/5xx counts as an error response (server rejected the request)
                    http_is_error = resp.status_code >= 400
                    try:
                        body = resp.json()
                    except Exception:
                        body = {}
                    err = body.get("error", {})
                    actual_code = err.get("code")
                    if expect_error_code is not None:
                        # Accept either the exact JSON-RPC error code or an HTTP error status
                        passed = actual_code == expect_error_code or http_is_error
                        return AssertionResult(
                            assertion_type="json_rpc",
                            passed=passed,
                            expected=str(expect_error_code),
                            actual=f"http={resp.status_code} code={actual_code}",
                            detail=f"raw_body error: expected code={expect_error_code}, got http={resp.status_code} code={actual_code}",
                            duration_ms=int((time.monotonic() - t0) * 1000),
                        )
                    # For expect_error: true — HTTP 4xx counts as an error
                    is_error = "error" in body or http_is_error
                    return AssertionResult(
                        assertion_type="json_rpc",
                        passed=is_error,
                        detail=f"raw_body → HTTP {resp.status_code}, error={err or resp.text[:80]}",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )

                # Normal JSON-RPC call
                resp = await client.post(
                    url,
                    json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                body = resp.json()

            # Error-expected checks
            if expect_error or expect_error_code is not None:
                err = body.get("error", {})
                if expect_error_code is not None:
                    actual_code = err.get("code")
                    passed = actual_code == expect_error_code
                    return AssertionResult(
                        assertion_type="json_rpc",
                        passed=passed,
                        expected=str(expect_error_code),
                        actual=str(actual_code),
                        detail=f"{method} error code: expected={expect_error_code} actual={actual_code}",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                passed = "error" in body
                return AssertionResult(
                    assertion_type="json_rpc",
                    passed=passed,
                    detail=f"{method}: {'error present' if passed else 'no error (expected error)'}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

            if "error" in body:
                err = body["error"]
                return AssertionResult(
                    assertion_type="json_rpc",
                    passed=False,
                    detail=f"{method} error: {err.get('message', err)}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

            result = body.get("result", {})

            # Field existence check
            if expect_has_field:
                passed = expect_has_field in result
                return AssertionResult(
                    assertion_type="json_rpc",
                    passed=passed,
                    expected=f"field '{expect_has_field}' present",
                    actual=str(list(result.keys()))[:200],
                    detail=f"{method}: field '{expect_has_field}' {'found' if passed else 'missing'}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

            # Count check
            if expect_count is not None or expect_count_exact is not None:
                data = result.get("data", [])
                actual_count = len(data)
                if expect_count_exact is not None:
                    passed = actual_count == expect_count_exact
                    exp_str = f"== {expect_count_exact} items"
                else:
                    passed = actual_count >= expect_count
                    exp_str = f">= {expect_count} items"
                first_param = params[0] if isinstance(params, list) and params else (params.get("application", "") if isinstance(params, dict) else "")
                return AssertionResult(
                    assertion_type="json_rpc",
                    passed=passed,
                    expected=exp_str,
                    actual=f"{actual_count} items",
                    detail=(
                        f"{method}({first_param}) → "
                        f"{actual_count} items (expected {exp_str})"
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
