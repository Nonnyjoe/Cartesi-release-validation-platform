"""Generic CLI runner — docker exec into the right sandbox container per binary.

Uses the docker SDK (already in requirements.txt) via the mounted /var/run/docker.sock.
Binaries are whitelisted to keep the blast radius narrow.

Container routing (v2.x sandbox topology):
  - `cartesi`              → rvp-cli-<short>       (docker:27-cli + npm @cartesi/cli)
  - `cartesi-rollups-cli`  → rvp-advancer-<short>  (cartesi/rollups-runtime image; also
                             tried: jsonrpc, validator — all run the same runtime image)
  - `cast` / `forge`       → rvp-anvil-<short>     (ghcr.io/foundry-rs/foundry image)
  - `sh`                   → rvp-cli-<short>       (alpine; no bash there)
  - `bash`                 → rvp-advancer-<short>  (debian-based runtime), falls back to
                             `sh` in rvp-cli-<short>

If the binary is missing in the first candidate container (exit code 126/127 or a
"not found" docker error), the next candidate is tried automatically.
"""
from __future__ import annotations

import asyncio
import logging
import shlex

import docker
from docker.errors import APIError, NotFound

log = logging.getLogger("ai-agent.cli_tool")

ALLOWED_BINARIES = {
    "cartesi":             "@cartesi/cli (npm) — build/deploy/address-book for v2.x apps",
    "cartesi-rollups-cli": "Cartesi rollups node CLI — app status, validate, execute, etc.",
    "cast":                "Foundry cast — send/call/parse Ethereum txs",
    "forge":               "Foundry forge — script/deploy Solidity",
    "bash":                "Shell wrapper (runtime containers) — use sparingly",
    "sh":                  "Shell wrapper (cli/alpine container) — use sparingly",
}

# Per-binary candidate container name templates, tried in order.
# {short} is the first 8 chars of the sandbox id; {short12} the first 12.
BINARY_ROUTES: dict[str, list[str]] = {
    "cartesi":             ["rvp-cli-{short}", "rvp-cli-{short12}"],
    "cartesi-rollups-cli": ["rvp-advancer-{short}", "rvp-jsonrpc-{short}", "rvp-validator-{short}"],
    "cast":                ["rvp-anvil-{short}"],
    "forge":               ["rvp-anvil-{short}"],
    "bash":                ["rvp-advancer-{short}", "rvp-cli-{short}"],
    "sh":                  ["rvp-cli-{short}", "rvp-advancer-{short}"],
}

TIMEOUT_S = 60.0

# Defence-in-depth (review §15 Security): `bash`/`sh` are whitelisted for
# legitimate recipes (env inspection, psql, curl), which is effectively arbitrary
# execution inside the sandbox container. This denylist blocks the catastrophic /
# blast-radius patterns outright. It is NOT a complete sandbox — full isolation
# (a brokered exec proxy + dropping docker.sock) is a separate hardening track,
# documented in the remediation log. Patterns are matched case-insensitively
# against the full command string.
import re as _re
_DESTRUCTIVE_PATTERNS = [
    _re.compile(p, _re.IGNORECASE) for p in (
        r"\brm\s+-rf?\s+(/|\$|~|\*|\.\.)",   # rm -rf / | $VAR | ~ | * | ..
        r"\bmkfs\b", r"\bdd\b.+\bof=/dev/", r":\s*\(\s*\)\s*\{",  # fork bomb
        r">\s*/dev/sd", r"\bshutdown\b", r"\breboot\b", r"\bhalt\b",
        r"\bchmod\s+-R\s+777\s+/", r"\b(curl|wget)\b.+\|\s*(ba)?sh\b",  # pipe-to-shell
        r"\bdocker\b", r"/var/run/docker\.sock",   # no docker-in-docker escapes
        r"\bnc\b\s+-l", r"\b(iptables|ip6tables)\b",
    )
]


def _destructive(cmd: str) -> str | None:
    for pat in _DESTRUCTIVE_PATTERNS:
        if pat.search(cmd):
            return pat.pattern
    return None

# Exit codes Docker/sh report when the executable itself can't be run
_NOT_FOUND_EXITS = {126, 127}

_client: docker.DockerClient | None = None


def _get_client() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def _candidate_containers(sandbox_id: str, binary: str, override: str | None) -> list[str]:
    """Ordered list of container names to try for this binary."""
    if override:
        return [override]
    if not sandbox_id:
        return []
    ctx = {"short": sandbox_id[:8], "short12": sandbox_id[:12]}
    return [tpl.format(**ctx) for tpl in BINARY_ROUTES.get(binary, ["rvp-cli-{short}"])]


def _run_exec(container_name: str, argv: list[str]) -> dict:
    client = _get_client()
    try:
        c = client.containers.get(container_name)
    except NotFound:
        return {"success": False, "not_found": True,
                "error": f"Container {container_name!r} not found"}
    try:
        result = c.exec_run(argv, stdout=True, stderr=True, demux=True)
    except APIError as exc:
        msg = str(exc)
        # "executable file not found in $PATH" surfaces as an APIError on some daemons
        binary_missing = "executable file not found" in msg or "no such file or directory" in msg
        return {"success": False, "binary_missing": binary_missing,
                "error": f"docker API error: {msg}", "container": container_name}
    exit_code = result.exit_code if result.exit_code is not None else -1
    stdout_b, stderr_b = result.output if isinstance(result.output, tuple) else (result.output, b"")
    stdout = (stdout_b or b"").decode(errors="replace")
    stderr = (stderr_b or b"").decode(errors="replace")
    out = {
        "success": exit_code == 0,
        "container": container_name,
        "exit_code": exit_code,
        "stdout": stdout[:6000],
        "stderr": stderr[:2000],
    }
    if exit_code in _NOT_FOUND_EXITS or "executable file not found" in stderr:
        out["binary_missing"] = True
    return out


async def run_cli_command(
    sandbox_id: str,
    binary: str,
    args: str,
    container: str | None = None,
) -> dict:
    if binary not in ALLOWED_BINARIES:
        return {
            "success": False,
            "error": f"Binary {binary!r} not whitelisted. Allowed: {sorted(ALLOWED_BINARIES)}",
        }
    # Block catastrophic shell patterns (bash/sh are dual-use; this is the
    # blast-radius guardrail — see _DESTRUCTIVE_PATTERNS).
    hit = _destructive(f"{binary} {args}")
    if hit:
        log.warning("run_cli_command BLOCKED destructive pattern %r in: %s %s", hit, binary, args[:120])
        return {"success": False, "denied": True,
                "error": f"Command blocked: matches a destructive-pattern guardrail ({hit}). "
                         "This tool is for test execution, not host/container administration."}
    try:
        argv = [binary, *shlex.split(args)]
    except ValueError as exc:
        return {"success": False, "error": f"invalid args: {exc}"}

    candidates = _candidate_containers(sandbox_id, binary, container)
    if not candidates:
        return {"success": False, "error": "No sandbox_id bound to this session and no container override given"}

    tried: list[dict] = []
    for name in candidates:
        log.info("run_cli_command: docker exec %s %s", name, " ".join(argv))
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_run_exec, name, argv),
                timeout=TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": f"timeout after {TIMEOUT_S}s", "container": name,
                    "binary": binary, "args": args}
        # Move on to the next candidate only when the container is missing or
        # the binary isn't present there; any other failure is a real result.
        if result.get("not_found") or result.get("binary_missing"):
            tried.append({"container": name, "error": result.get("error") or result.get("stderr", "")[:200]})
            continue
        result["binary"] = binary
        result["args"] = args
        return result

    return {
        "success": False,
        "binary": binary,
        "args": args,
        "error": (
            f"{binary!r} not runnable in any candidate container. "
            f"Tried: {[t['container'] for t in tried]}. "
            "Hint: `cartesi` lives in rvp-cli-*, `cartesi-rollups-cli` in the runtime "
            "containers (rvp-advancer-*/rvp-jsonrpc-*), `cast`/`forge` in rvp-anvil-*."
        ),
        "attempts": tried,
    }
