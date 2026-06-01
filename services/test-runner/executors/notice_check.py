"""
services/test-runner/executors/notice_check.py
Assertion type: notice_check

Polls cartesi_listOutputs until at least one Notice output is found whose
decoded payload matches the specified criteria.

Assertion YAML:
  - type: notice_check
    min_count: 1              # minimum number of notices expected (default 1)
    contains_text: ""         # optional: hex-decoded payload must contain this string
    poll_interval: 3          # seconds between polls (default 3)
    poll_timeout: 60          # total timeout in seconds (default 60)
"""
import asyncio
import json
import logging
import time
import httpx

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.notice_check")


class NoticeCheckExecutor(AssertionExecutor):
    assertion_type = "notice_check"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        min_count      = int(assertion.get("min_count", 1))
        contains_text  = assertion.get("contains_text", "")
        poll_interval  = float(assertion.get("poll_interval", 3))
        poll_timeout   = float(assertion.get("poll_timeout", 60))

        app_id  = ctx.app_address or "app"
        rpc_url = ctx.jsonrpc_rpc_url
        t0      = time.monotonic()
        deadline = t0 + poll_timeout

        while time.monotonic() < deadline:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        rpc_url,
                        json={
                            "jsonrpc": "2.0",
                            "method":  "cartesi_listOutputs",
                            "params":  [app_id],
                            "id": 1,
                        },
                    )
                    body = resp.json()

                if "error" in body:
                    await asyncio.sleep(poll_interval)
                    continue

                outputs = body.get("result", {}).get("data", [])
                notices = [o for o in outputs if
                           o.get("__typename") == "Notice"
                           or o.get("type") == "Notice"
                           or "notice" in str(o.get("__typename", "")).lower()
                           or o.get("output_enum") == "Notice"
                           or o.get("decoded_data", {}).get("type") == "Notice"]

                # Fallback: any output without a destination/value is likely a notice
                if not notices:
                    notices = [o for o in outputs if not o.get("destination")
                               and not o.get("decoded_data", {}).get("destination")]

                matching = notices
                if contains_text:
                    def _matches(o):
                        payload_hex = o.get("payload", o.get("raw_data", "0x"))
                        try:
                            decoded = bytes.fromhex(
                                payload_hex.removeprefix("0x")
                            ).decode("utf-8", errors="replace")
                            return contains_text in decoded
                        except Exception:
                            return False
                    matching = [o for o in notices if _matches(o)]

                duration_ms = int((time.monotonic() - t0) * 1000)

                if len(matching) >= min_count:
                    sample = matching[0]
                    payload_hex = sample.get("payload", sample.get("raw_data", "0x"))
                    try:
                        decoded = bytes.fromhex(
                            payload_hex.removeprefix("0x")
                        ).decode("utf-8", errors="replace")[:120]
                    except Exception:
                        decoded = payload_hex[:120]
                    return AssertionResult(
                        assertion_type="notice_check",
                        passed=True,
                        expected=f">= {min_count} notice(s)",
                        actual=f"{len(matching)} matching notice(s)",
                        detail=f"First notice: {decoded}",
                        duration_ms=duration_ms,
                    )

            except Exception as exc:
                log.debug("notice_check poll error: %s", exc)

            await asyncio.sleep(poll_interval)

        duration_ms = int((time.monotonic() - t0) * 1000)
        return AssertionResult(
            assertion_type="notice_check",
            passed=False,
            expected=f">= {min_count} notice(s)" + (f" containing {contains_text!r}" if contains_text else ""),
            actual="0 matching notices after timeout",
            detail=f"Timed out after {poll_timeout}s waiting for notices",
            duration_ms=duration_ms,
        )
