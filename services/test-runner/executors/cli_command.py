"""
services/test-runner/executors/cli_command.py
Assertion type: cli_command

Runs a CLI command inside the sandbox's cli-tools container and validates
the output and exit code.

The cli-tools container is named:  rvp-cli-{sandbox_id[:8]}
It must be running (provisioned with a cli_version).

Assertion YAML:
  - type: cli_command
    args: "address-book"            # CLI subcommand + args string (no binary prefix)
    binary: "cartesi"               # optional; default "cartesi"; use "cartesi-rollups-cli" for internal CLI
    container: "rvp-cli-{short}"    # optional; overrides default container name
    expect_exit_code: 0             # default 0 (success)
    expect_output_contains: ""      # optional substring in stdout+stderr
    expect_output_not_contains: ""  # optional: must NOT contain this string
    timeout: 30                     # seconds (default 30)

Template variables available in args:
  {anvil_rpc_url}          → container-internal anvil RPC URL (http://rvp-anvil-{short}:8545)
  {app_address}            → deployed application contract address
  {inputbox_address}       → InputBox contract address
  {erc20_token_address}    → pre-deployed ERC20 test token address
  {erc721_token_address}   → pre-deployed ERC721 test token address
  {erc1155_token_address}  → pre-deployed ERC1155 test token address
"""
import logging
import subprocess
import time

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.cli_command")


class CliCommandExecutor(AssertionExecutor):
    assertion_type = "cli_command"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_sync, assertion, ctx)

    def _run_sync(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        args_raw    = assertion.get("args", "")
        binary      = assertion.get("binary", "cartesi")
        expect_code = int(assertion.get("expect_exit_code", 0))
        expect_out  = assertion.get("expect_output_contains", "")
        expect_not  = assertion.get("expect_output_not_contains", "")
        timeout_s   = int(assertion.get("timeout", 30))
        short       = ctx.sandbox_id[:8]

        # Resolve template variables in args and container fields
        template_vars = {
            "anvil_rpc_url":         f"http://rvp-anvil-{short}:8545",
            "app_address":           ctx.app_address or "",
            "inputbox_address":      ctx.inputbox_address or "",
            "erc20_token_address":   ctx.erc20_token_address or "",
            "erc721_token_address":  ctx.erc721_token_address or "",
            "erc1155_token_address": ctx.erc1155_token_address or "",
            "jsonrpc_container":     f"rvp-jsonrpc-{short}",
        }
        if isinstance(args_raw, str):
            for var, val in template_vars.items():
                args_raw = args_raw.replace(f"{{{var}}}", val)
            args = args_raw.split()
        else:
            args = [str(a) for a in args_raw]

        # Prefer explicit container name from assertion (supports template vars),
        # then context cli_container_name, then naming convention
        container_tpl = assertion.get("container") or ctx.cli_container_name or f"rvp-cli-{short}"
        for var, val in template_vars.items():
            container_tpl = container_tpl.replace(f"{{{var}}}", val)
        cli_container = container_tpl

        cmd = ["docker", "exec", cli_container, binary] + args
        t0  = time.monotonic()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            output      = (result.stdout or "") + (result.stderr or "")
            duration_ms = int((time.monotonic() - t0) * 1000)
            exit_code   = result.returncode

            if exit_code != expect_code:
                return AssertionResult(
                    assertion_type="cli_command",
                    passed=False,
                    expected=f"exit {expect_code}",
                    actual=f"exit {exit_code}",
                    detail=f"{binary} {' '.join(args)}: exit={exit_code}\n{output[:300]}",
                    duration_ms=duration_ms,
                )

            if expect_out and expect_out not in output:
                return AssertionResult(
                    assertion_type="cli_command",
                    passed=False,
                    expected=f"output contains {expect_out!r}",
                    actual=output[:300],
                    detail=f"{binary} {' '.join(args)}: missing expected output",
                    duration_ms=duration_ms,
                )

            if expect_not and expect_not in output:
                return AssertionResult(
                    assertion_type="cli_command",
                    passed=False,
                    expected=f"output does NOT contain {expect_not!r}",
                    actual=output[:300],
                    detail=f"{binary} {' '.join(args)}: unexpected string in output",
                    duration_ms=duration_ms,
                )

            return AssertionResult(
                assertion_type="cli_command",
                passed=True,
                detail=f"{binary} {' '.join(args)} → exit=0; {output[:120]}",
                duration_ms=duration_ms,
            )

        except subprocess.TimeoutExpired:
            return AssertionResult(
                assertion_type="cli_command",
                passed=False,
                detail=f"{binary} {' '.join(args)} timed out ({timeout_s}s)",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            log.warning("cli_command error: %s", exc)
            return AssertionResult(
                assertion_type="cli_command",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
