"""
shared/sdk_resolver.py

Resolves the @cartesi/sdk version and @cartesi/cli version for a given
rollups-node release tag.

How the mapping works
---------------------
Each `@cartesi/cli` release targets a specific rollups-node version.
The CLI release body mentions the rollups-node version it bumps (e.g.
"bump rollups-node to v2.0.0-alpha.11"), AND the SDK version is
published as @cartesi/sdk@<sdk_version> in the same release.
That sdk_version string is the exact Docker image tag:
  cartesi/rollups-runtime:<sdk_version>
  cartesi/rollups-database:<sdk_version>

And the CLI release tag itself (e.g. v2.0.0-alpha.34) is the CLI version
that should be installed when testing that rollups-node release.

Both the SDK version and CLI version can be resolved from the same CLI
release body, so _scan_cli_releases() makes a single GitHub API call and
returns both.
"""
import logging
import os
import re

import httpx

log = logging.getLogger("rvp.sdk_resolver")

# ── Static SDK lookup (confirmed from CLI release notes) ──────────────────────
# key  = rollups-node version without 'v' prefix
# value = @cartesi/sdk version == Docker image tag suffix
KNOWN: dict[str, str] = {
    "2.0.0-alpha.11": "0.12.0-alpha.39",
    "2.0.0-alpha.9":  "0.12.0-alpha.27",
    "2.0.0-alpha.8":  "0.12.0-alpha.23",
    "2.0.0-alpha.7":  "0.12.0-alpha.22",
}

# ── Static CLI version lookup (confirmed from CLI release notes) ───────────────
# key  = rollups-node version without 'v' prefix
# value = @cartesi/cli version that ships with this node version
KNOWN_CLI: dict[str, str] = {
    "2.0.0-alpha.11": "2.0.0-alpha.34",
    "2.0.0-alpha.9":  "2.0.0-alpha.22",
    "2.0.0-alpha.8":  "2.0.0-alpha.19",
    "2.0.0-alpha.7":  "2.0.0-alpha.13",
}

KNOWN_DEVNET: dict[str, str] = {}
KNOWN_CONTRACTS: dict[str, str] = {}

GH_API = "https://api.github.com"

# CLI GitHub repository — configurable so forks / mirrors can be tracked
# without code changes. Matches the GITHUB_REPO convention used by the watcher.
CLI_GITHUB_REPO      = os.environ.get("CLI_GITHUB_REPO", "cartesi/cli")
CLI_RELEASES_URL     = f"{GH_API}/repos/{CLI_GITHUB_REPO}/releases"
CONTRACTS_GITHUB_REPO = os.environ.get("CONTRACTS_GITHUB_REPO", "cartesi/rollups-contracts")

GH_HEADERS       = {
    "Accept":               "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Patterns to find sdk version inside a CLI release body
_SDK_PATTERNS = [
    re.compile(r'@cartesi/sdk[@: ]+(\d+\.\d+\.\d+(?:-\w+\.\d+)?)', re.IGNORECASE),
    re.compile(r'cartesi/rollups-runtime:(\d+\.\d+\.\d+(?:-\w+\.\d+)?)', re.IGNORECASE),
    re.compile(r'cartesi/rollups-database:(\d+\.\d+\.\d+(?:-\w+\.\d+)?)', re.IGNORECASE),
]

# Pattern to match a rollups-node version bump mention in a CLI release body
_NODE_BUMP_RE = re.compile(
    r'rollups[- ]node[^0-9]*v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)', re.IGNORECASE
)

_DEVNET_IN_BODY_RE = re.compile(
    r'@cartesi/devnet[@: ]+v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)', re.IGNORECASE
)
_CONTRACTS_IN_BODY_RE = re.compile(
    r'(?:@cartesi/rollups-contracts|rollups-contracts)[@: ]+v?(\d+\.\d+\.\d+(?:-\w+\.\d+)?)',
    re.IGNORECASE,
)


def _extract_sdk_from_body(body: str) -> str | None:
    """Return first SDK version found in a release body string."""
    for pat in _SDK_PATTERNS:
        m = pat.search(body)
        if m:
            return m.group(1)
    return None


def extract_versions_from_cli_body(
    body: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Parse a @cartesi/cli release body and return:
      (sdk_version, devnet_version, contracts_version, node_version_targeted)

    All version strings are returned WITHOUT a 'v' prefix — callers apply
    the correct prefix convention for each catalog table.

    Returns (None, None, None, None) if the body is empty or unparseable.
    """
    sdk_version       = _extract_sdk_from_body(body)
    devnet_m          = _DEVNET_IN_BODY_RE.search(body)
    devnet_version    = devnet_m.group(1) if devnet_m else None
    contracts_m       = _CONTRACTS_IN_BODY_RE.search(body)
    contracts_version = contracts_m.group(1) if contracts_m else None
    node_m            = _NODE_BUMP_RE.search(body)
    node_version      = node_m.group(1) if node_m else None
    return sdk_version, devnet_version, contracts_version, node_version


async def _scan_cli_releases(
    node_ver: str,
    github_token: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Scan the cartesi/cli GitHub releases for those that target node_ver.

    Returns (sdk_version, cli_version, devnet_version, contracts_version).
    The values are collected independently across all matching releases — the
    SDK version, CLI version, devnet version, and contracts version may appear
    in different releases on the same page (e.g. separate @cartesi/sdk and
    @cartesi/cli tags that both reference the same rollups-node bump).
    Scanning continues until sdk+cli are found or the full page is exhausted;
    devnet/contracts are collected along the way.

    Makes exactly one GitHub API call.
    Updates the in-process caches (KNOWN, KNOWN_CLI, KNOWN_DEVNET,
    KNOWN_CONTRACTS) on a successful match.
    """
    headers = dict(GH_HEADERS)
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                CLI_RELEASES_URL, headers=headers, params={"per_page": "100"}
            )
            if resp.status_code != 200:
                log.warning("CLI releases API returned %d", resp.status_code)
                return None, None, None, None
            cli_releases = resp.json()
    except Exception as exc:
        log.warning("Could not fetch CLI releases: %s", exc)
        return None, None, None, None

    found_sdk: str | None = None
    found_cli: str | None = None
    found_devnet: str | None = None
    found_contracts: str | None = None

    # Scan every release on the page — the SDK version and CLI version may appear
    # in different releases (e.g. separate @cartesi/sdk and @cartesi/cli tags)
    # that both describe the same rollups-node version bump.  Collect
    # independently and stop only when both sdk+cli are in hand.
    for rel in cli_releases:
        body = rel.get("body") or ""
        bump = _NODE_BUMP_RE.search(body)
        if not (bump and bump.group(1) == node_ver):
            continue

        # This release references our rollups-node version.
        cli_tag = rel.get("tag_name", "").lstrip("v")
        if cli_tag and not found_cli:
            found_cli = cli_tag

        sdk = _extract_sdk_from_body(body)
        if sdk and not found_sdk:
            found_sdk = sdk

        devnet_m = _DEVNET_IN_BODY_RE.search(body)
        devnet = devnet_m.group(1) if devnet_m else None
        if devnet and not found_devnet:
            found_devnet = devnet

        contracts_m = _CONTRACTS_IN_BODY_RE.search(body)
        contracts = contracts_m.group(1) if contracts_m else None
        if contracts and not found_contracts:
            found_contracts = contracts

        if found_cli and found_sdk:
            break   # primary versions resolved — no need to keep scanning

    if found_cli or found_sdk:
        log.info(
            "Resolved via CLI releases: node=%s sdk=%s cli=%s devnet=%s contracts=%s",
            node_ver, found_sdk, found_cli, found_devnet, found_contracts,
        )
        if found_sdk:
            KNOWN[node_ver] = found_sdk
        if found_cli:
            KNOWN_CLI[node_ver] = found_cli
        if found_devnet:
            KNOWN_DEVNET[node_ver] = found_devnet
        if found_contracts:
            KNOWN_CONTRACTS[node_ver] = found_contracts
    else:
        log.warning(
            "Could not resolve versions for rollups-node %s via CLI releases", node_ver
        )

    return found_sdk, found_cli, found_devnet, found_contracts


async def resolve_sdk_version(node_tag: str, github_token: str = "") -> str | None:
    """
    Return the @cartesi/sdk version for a given rollups-node release tag.

    Args:
        node_tag:     e.g. "v2.0.0-alpha.11" or "2.0.0-alpha.11"
        github_token: optional Bearer token to avoid rate limits

    Returns:
        SDK version string like "0.12.0-alpha.39", or None if unknown.
    """
    node_ver = node_tag.lstrip("v")

    if node_ver in KNOWN:
        return KNOWN[node_ver]

    log.debug("SDK version not in static map for %s — querying GitHub", node_tag)
    sdk, _, _, _ = await _scan_cli_releases(node_ver, github_token)
    return sdk


async def resolve_cli_version(node_tag: str, github_token: str = "") -> str | None:
    """
    Return the @cartesi/cli version for a given rollups-node release tag.

    Args:
        node_tag:     e.g. "v2.0.0-alpha.11" or "2.0.0-alpha.11"
        github_token: optional Bearer token to avoid rate limits

    Returns:
        CLI version string like "2.0.0-alpha.34", or None if unknown.
    """
    node_ver = node_tag.lstrip("v")

    if node_ver in KNOWN_CLI:
        return KNOWN_CLI[node_ver]

    log.debug("CLI version not in static map for %s — querying GitHub", node_tag)
    _, cli, _, _ = await _scan_cli_releases(node_ver, github_token)
    return cli


async def resolve_versions(
    node_tag: str,
    github_token: str = "",
) -> tuple[str | None, str | None]:
    """
    Return (sdk_version, cli_version) for a v2.x rollups-node release tag.

    Prefer this over calling resolve_sdk_version + resolve_cli_version separately —
    it makes at most one GitHub API call since both values come from the same
    CLI release body.

    Args:
        node_tag:     e.g. "v2.0.0-alpha.11"
        github_token: optional Bearer token

    Returns:
        (sdk_version, cli_version) — either may be None if unknown.
    """
    node_ver = node_tag.lstrip("v")

    sdk = KNOWN.get(node_ver)
    cli = KNOWN_CLI.get(node_ver)

    if sdk and cli:
        return sdk, cli   # both cached — no API call needed

    # At least one is missing; scan GitHub once for both
    scanned_sdk, scanned_cli, _, _ = await _scan_cli_releases(node_ver, github_token)
    return sdk or scanned_sdk, cli or scanned_cli


async def resolve_all_versions(
    node_tag: str,
    github_token: str = "",
) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Return (sdk_version, cli_version, devnet_version, contracts_version) for a rollups-node tag.
    Makes at most one GitHub API call.
    """
    node_ver = node_tag.lstrip("v")

    sdk       = KNOWN.get(node_ver)
    cli       = KNOWN_CLI.get(node_ver)
    devnet    = KNOWN_DEVNET.get(node_ver)
    contracts = KNOWN_CONTRACTS.get(node_ver)

    if sdk and cli:
        return sdk, cli, devnet, contracts

    scanned_sdk, scanned_cli, scanned_devnet, scanned_contracts = await _scan_cli_releases(
        node_ver, github_token
    )
    return (
        sdk or scanned_sdk,
        cli or scanned_cli,
        devnet or scanned_devnet,
        contracts or scanned_contracts,
    )


def derive_image_tag(node_tag: str, sdk_version: str | None) -> str:
    """
    Return the correct Docker image tag for a release.

    v1.x → Docker Hub, no 'v' prefix:  cartesi/rollups-node:1.5.1
    v2.x → SDK runtime image:           cartesi/rollups-runtime:0.12.0-alpha.39
    """
    ver = node_tag.lstrip("v")
    try:
        major = int(ver.split(".")[0])
    except (ValueError, IndexError):
        major = 1

    if major >= 2 and sdk_version:
        return f"cartesi/rollups-runtime:{sdk_version}"

    # v1.x (or v2.x without a known SDK — fallback)
    return f"cartesi/rollups-node:{ver}"


def node_major_version(node_tag: str) -> int:
    """Return the major version integer for a release tag."""
    ver = node_tag.lstrip("v")
    try:
        return int(ver.split(".")[0])
    except (ValueError, IndexError):
        return 1
