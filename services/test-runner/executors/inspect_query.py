"""
services/test-runner/executors/inspect_query.py
Assertion type: inspect_query

POSTs a query string to the Cartesi inspect endpoint and validates the
decoded report payload. The payload is expected to be a hex-encoded UTF-8
JSON string emitted by the application via rollup.report().

Endpoint: POST http://{inspect_host}:{inspect_port}/inspect/{app_address}/{query}
           (or GET with ?payload=<query>)

Assertion YAML:
  - type: inspect_query
    query: "all"                          # inspect payload sent to the app
    method: "POST"                        # POST (default) | GET
    expect_json_field: "route"            # optional: dotted path into parsed JSON
    expect_json_value: "all"              # optional: expected value at path
    expect_contains: "students"           # optional: substring in raw response body
    expect_status: 200                    # default 200
    app_address_override: "0xdeadbeef..."  # override ctx.app_address for this call
    use_app_name: false                   # if true, use "app" as name instead of 0x address
    concurrent: 50                        # send N concurrent requests, all must succeed
"""
import asyncio
import json
import logging
import re
import time
import httpx

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.inspect_query")


def _resolve(obj, path: str):
    for part in re.split(r"\.|(\[\d+\])", path):
        if not part:
            continue
        if part.startswith("["):
            obj = obj[int(part[1:-1])]
        else:
            obj = obj[part]
    return obj


class InspectQueryExecutor(AssertionExecutor):
    assertion_type = "inspect_query"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        query           = assertion.get("query", "all")
        method          = assertion.get("method", "POST").upper()
        expect_field    = assertion.get("expect_json_field")
        expect_value    = assertion.get("expect_json_value")
        expect_contains = assertion.get("expect_contains")
        expect_status   = int(assertion.get("expect_status", 200))
        addr_override   = assertion.get("app_address_override")
        use_app_name    = assertion.get("use_app_name", False)
        concurrent      = assertion.get("concurrent")

        # Build the URL.
        # v2 inspect API: POST /inspect/{app} with query in the request body.
        # GET variant:    GET  /inspect/{app}/{query} (query in path, no body).
        base = ctx.inspect_url
        app_id = addr_override or ("app" if use_app_name else ctx.app_address)
        if method.upper() == "GET":
            # GET: query goes in the URL path
            if app_id:
                url = f"{base}/{app_id}/{query}".rstrip("/")
            else:
                url = f"{base}/{query}".rstrip("/")
        else:
            # POST: query goes in the request body; URL only contains app identifier
            if app_id:
                url = f"{base}/{app_id}".rstrip("/")
            else:
                url = base

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Concurrent mode: fire N requests in parallel
                if concurrent:
                    async def _req():
                        if method == "GET":
                            return await client.get(url)
                        return await client.post(url, content=query.encode(), headers={"Content-Type": "text/plain"})

                    responses = await asyncio.gather(*[_req() for _ in range(concurrent)], return_exceptions=True)
                    errors = [r for r in responses if isinstance(r, Exception)]
                    non_ok = [r for r in responses if not isinstance(r, Exception) and r.status_code != expect_status]
                    passed = len(errors) == 0 and len(non_ok) == 0
                    return AssertionResult(
                        assertion_type="inspect_query",
                        passed=passed,
                        detail=(
                            f"inspect {query!r} × {concurrent}: "
                            f"{len(errors)} exceptions, {len(non_ok)} non-{expect_status} responses"
                        ),
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )

                if method == "GET":
                    resp = await client.get(url)
                else:
                    resp = await client.post(
                        url,
                        content=query.encode(),
                        headers={"Content-Type": "text/plain"},
                    )

            duration_ms = int((time.monotonic() - t0) * 1000)

            if resp.status_code != expect_status:
                return AssertionResult(
                    assertion_type="inspect_query",
                    passed=False,
                    expected=f"HTTP {expect_status}",
                    actual=f"HTTP {resp.status_code}",
                    detail=f"inspect {query!r} → HTTP {resp.status_code}",
                    duration_ms=duration_ms,
                )

            # For non-200 expected status, the status match is sufficient — don't
            # try to parse the body (error responses are often not JSON).
            if expect_status != 200:
                return AssertionResult(
                    assertion_type="inspect_query",
                    passed=True,
                    detail=f"inspect {query!r} → HTTP {resp.status_code} (expected)",
                    duration_ms=duration_ms,
                )

            body = resp.json()

            # Decode the hex payload from the first report
            raw_report = ""
            reports = body.get("reports", [])
            if reports:
                hex_payload = reports[0].get("payload", "0x")
                raw_bytes = bytes.fromhex(hex_payload.removeprefix("0x"))
                raw_report = raw_bytes.decode("utf-8", errors="replace")

            # Optional substring check
            if expect_contains and expect_contains not in raw_report:
                return AssertionResult(
                    assertion_type="inspect_query",
                    passed=False,
                    expected=f"contains {expect_contains!r}",
                    actual=raw_report[:300],
                    detail=f"inspect {query!r} response missing expected text",
                    duration_ms=duration_ms,
                )

            # Optional JSON field check
            if expect_field is not None:
                try:
                    parsed = json.loads(raw_report)
                    actual_val = _resolve(parsed, expect_field)
                    passed = (actual_val == expect_value)
                    return AssertionResult(
                        assertion_type="inspect_query",
                        passed=passed,
                        expected=expect_value,
                        actual=actual_val,
                        detail=f"inspect {query!r}: {expect_field}={actual_val!r}",
                        duration_ms=duration_ms,
                    )
                except Exception as exc:
                    return AssertionResult(
                        assertion_type="inspect_query",
                        passed=False,
                        detail=f"inspect {query!r}: JSON parse error — {exc}; raw={raw_report[:200]}",
                        duration_ms=duration_ms,
                    )

            return AssertionResult(
                assertion_type="inspect_query",
                passed=True,
                detail=f"inspect {query!r} → OK ({len(reports)} report(s)); {raw_report[:120]}",
                duration_ms=duration_ms,
            )

        except Exception as exc:
            log.warning("inspect_query error: %s", exc)
            return AssertionResult(
                assertion_type="inspect_query",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
