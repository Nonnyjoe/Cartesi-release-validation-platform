"""
tools/__init__.py
Exports AGENT_TOOLS — the list of tool schemas passed to the Claude API.
Also exports the executor registry used by tool_executor.py.
"""
from typing import Any

# ── Tool schemas (Claude API format) ─────────────────────────────────────────

AGENT_TOOLS: list[dict] = [
    {
        "name": "send_advance_input",
        "description": (
            "Send an advance-state input to the Cartesi node via the HTTP bridge. "
            "This submits a payload to the InputBox and triggers Cartesi Machine execution. "
            "Use this to test how the node processes inputs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "payload": {
                    "type": "string",
                    "description": "Hex-encoded payload to send, e.g. '0xdeadbeef'",
                },
                "app_address": {
                    "type": "string",
                    "description": "Target dApp contract address (defaults to test dApp)",
                    "default": "0x0000000000000000000000000000000000000001",
                },
            },
            "required": ["payload"],
        },
    },
    {
        "name": "query_graphql",
        "description": (
            "Execute a GraphQL query against the Cartesi node GraphQL API. "
            "Use this to inspect inputs, outputs, vouchers, notices, epochs, and claims. "
            "Always use this to verify state after sending inputs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The full GraphQL query string",
                },
                "variables": {
                    "type": "object",
                    "description": "Optional GraphQL variables",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "call_inspect",
        "description": (
            "Send a synchronous inspect-state REST request to the node. "
            "Does NOT create an L1 transaction. "
            "Use this to read dApp state without side effects."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "payload": {
                    "type": "string",
                    "description": "Hex-encoded inspect payload, e.g. '0x' for empty",
                },
            },
            "required": ["payload"],
        },
    },
    {
        "name": "read_logs",
        "description": (
            "Read stdout/stderr logs from a sandbox container. v2.x sandboxes run "
            "separate containers per node service: advancer, claimer, validator, "
            "jsonrpc, evm-reader, plus anvil, cli, db. 'node' falls back to the "
            "advancer/jsonrpc containers. "
            "Essential for diagnosing failures and confirming expected behaviour."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "component": {
                    "type": "string",
                    "enum": ["node", "anvil", "advancer", "claimer", "validator",
                             "jsonrpc", "evm-reader", "cli", "db"],
                    "description": "Which container to read logs from",
                },
                "tail": {
                    "type": "integer",
                    "description": "Number of log lines to retrieve (default 100)",
                    "default": 100,
                },
            },
            "required": ["component"],
        },
    },
    {
        "name": "run_cast_command",
        "description": (
            "Execute a raw Foundry cast command against the Anvil chain. Runs via "
            "docker exec inside the sandbox's Anvil container. "
            "Provide everything after 'cast', e.g. 'block-number' or "
            "'call 0x59b2... \"inputs()\"'. "
            "--rpc-url http://localhost:8545 is added automatically if not present."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The cast subcommand and args (without 'cast' prefix)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "generate_payload",
        "description": (
            "Generate a test payload for advance-state inputs. "
            "Use different modes to test edge cases: "
            "random (default), zero, boundary (0x00/0xFF mix), "
            "malformed (invalid sequences), structured (ABI-like), empty."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["random", "zero", "boundary", "malformed", "structured", "empty"],
                    "description": "Type of payload to generate",
                    "default": "random",
                },
                "size_bytes": {
                    "type": "integer",
                    "description": "Payload size in bytes (default 32)",
                    "default": 32,
                },
                "structured_type": {
                    "type": "string",
                    "enum": ["uint256", "address", "string", "bytes32"],
                    "description": "ABI type for structured mode",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_node_state",
        "description": (
            "Get a full snapshot of the node state: input count, epoch status, "
            "voucher count, notice count, and health check. "
            "Always call this at the start and end of an autonomous session."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "verify_voucher",
        "description": (
            "Fetch a voucher by input index and voucher index from GraphQL "
            "and verify it has a valid Merkle proof. "
            "A voucher without a proof cannot be executed on L1 yet "
            "(the epoch containing it hasn't been claimed)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "input_index": {
                    "type": "integer",
                    "description": "The input index that generated the voucher",
                },
                "voucher_index": {
                    "type": "integer",
                    "description": "The voucher index within that input (usually 0)",
                },
            },
            "required": ["input_index", "voucher_index"],
        },
    },
    {
        "name": "advance_time",
        "description": (
            "Mine N blocks on Anvil to advance chain time. "
            "Mining 7200 blocks closes one epoch and triggers the authority-claimer "
            "to submit a claim. Use this to test epoch close and voucher proof generation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "blocks": {
                    "type": "integer",
                    "description": "Number of blocks to mine (7200 = one epoch)",
                },
            },
            "required": ["blocks"],
        },
    },
    {
        "name": "report_finding",
        "description": (
            "Record an anomaly, bug, or unexpected behaviour observed during testing. "
            "Call this immediately whenever you observe something that doesn't match "
            "expected node behaviour. Include as much evidence as possible."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short, specific title describing the issue",
                },
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low", "info"],
                    "description": "Severity level of the finding",
                },
                "component": {
                    "type": "string",
                    "enum": ["dispatcher", "authority-claimer", "graphql-server",
                             "inspect-server", "anvil", "unknown"],
                    "description": "Which node component is affected",
                },
                "description": {
                    "type": "string",
                    "description": "Full description of what was observed and why it's unexpected",
                },
                "evidence": {
                    "type": "object",
                    "description": "Supporting evidence: log excerpts, GraphQL responses, etc.",
                },
                "reproduction_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Step-by-step instructions to reproduce the issue",
                },
            },
            "required": ["title", "severity", "component", "description"],
        },
    },
    # ── New AI-operator tools (added by AI Session integration) ──────────────
    {
        "name": "trigger_test",
        "description": (
            "Run a whitelisted test definition with parameter overrides chosen by you. "
            "Only definitions flagged `ai_allowed: true` are accepted. Overrides are merged "
            "into the assertion array by leaf-name (e.g. `payload`, `min_count`, `expect_count`). "
            "Returns once the test completes or `wait_seconds` elapses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "definition_slug": {
                    "type": "string",
                    "description": "The test slug (e.g. 'echo-ping-v2'). See the project knowledge "
                                   "test-catalog for whitelisted slugs.",
                },
                "parameter_overrides": {
                    "type": "object",
                    "description": "Map of leaf parameter names to override values "
                                   "(e.g. {\"payload\": \"0xCAFE\", \"min_count\": 3}).",
                    "default": {},
                },
                "wait_seconds": {
                    "type": "integer",
                    "description": "Seconds to wait for the test result. 0 = fire and forget.",
                    "default": 90,
                },
            },
            "required": ["definition_slug"],
        },
    },
    {
        "name": "read_test_definition",
        "description": (
            "Fetch the parsed YAML and metadata for a whitelisted test, so you can see what "
            "parameters are overridable before calling trigger_test."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "definition_slug": {"type": "string"},
            },
            "required": ["definition_slug"],
        },
    },
    {
        "name": "run_cli_command",
        "description": (
            "Run a whitelisted binary inside the right sandbox container via docker exec. "
            "Routing is automatic: `cartesi` (the npm @cartesi/cli) runs in the cli-tools "
            "container; `cartesi-rollups-cli` runs in the rollups runtime containers "
            "(advancer/jsonrpc); `cast`/`forge` run in the Anvil (Foundry) container; "
            "`bash`/`sh` run in the runtime/cli containers respectively. "
            "Common uses: `cartesi-rollups-cli app status`, "
            "`cast call <addr> 'sig(args)' <args>` (RPC inside the container is "
            "http://localhost:8545)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "binary": {
                    "type": "string",
                    "enum": ["cartesi", "cartesi-rollups-cli", "cast", "forge", "bash", "sh"],
                },
                "args": {
                    "type": "string",
                    "description": "Arguments string passed to the binary (shell-split client-side).",
                },
                "container": {
                    "type": "string",
                    "description": "Override the container name (skips automatic routing).",
                },
            },
            "required": ["binary", "args"],
        },
    },
    {
        "name": "call_jsonrpc",
        "description": (
            "Call a cartesi_* JSON-RPC method on the sandbox's JSON-RPC API (port 10011). "
            "Method must start with `cartesi_`. See the project knowledge "
            "cartesi-jsonrpc-quickref for the supported methods."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "JSON-RPC method, e.g. 'cartesi_listApplications', "
                                   "'cartesi_getEpoch', 'cartesi_listOutputs'.",
                },
                "params": {
                    "description": "List or object of params for the method.",
                },
            },
            "required": ["method"],
        },
    },
    {
        "name": "query_db",
        "description": (
            "Run a read-only SQL SELECT against the project's Postgres. The connection runs as "
            "the `ai_reader` role with SELECT on: tests.definitions, tests.results, "
            "orchestrator.runs, ai.sessions, ai.tool_invocations, ai.suggested_test_actions. "
            "Statement timeout 5s; max 200 rows returned. INSERT/UPDATE/DELETE will fail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT statement."},
            },
            "required": ["sql"],
        },
    },
    {
        "name": "provision_sandbox",
        "description": (
            "Request a new sandbox from the orchestrator. Returns the new run_id. Use when "
            "you need a fresh node to bootstrap from scratch — e.g. to reproduce a bug or "
            "explore startup behavior."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "release_tag":  {"type": "string", "default": "latest"},
                "image_tag":    {"type": "string", "default": "latest"},
                "app_id":       {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "teardown_sandbox",
        "description": (
            "Cancel an in-progress run so the sandbox-manager frees its containers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "lookup_skill",
        "description": (
            "Read a section of a Cartesi Skill markdown for deep knowledge not covered by "
            "the project knowledge in the system prompt. Call without `section` first to "
            "list available sections, then call again with the chosen heading."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "enum": [
                        "cartesi-scaffold", "cartesi-backend-core",
                        "cartesi-python-backend", "cartesi-js-backend",
                        "cartesi-frontend", "cartesi-l1-contracts",
                        "cartesi-jsonrpc", "cartesi-local-dev",
                        "cartesi-deploy", "cartesi-debug",
                    ],
                },
                "section": {
                    "type": "string",
                    "description": "Exact H2 heading text (case-insensitive). Omit to list headings.",
                },
            },
            "required": ["skill_name"],
        },
    },
]


# ─── Chaos Mode Tools (appended) ──────────────────────────────────────────────

CHAOS_TOOLS = [
    {
        "name": "restart_component",
        "description": (
            "Stop and restart a named container inside the sandbox to test node recovery. "
            "Valid components: 'node', 'anvil'. Use to simulate crashes and verify the node "
            "recovers state correctly after a restart."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "component": {
                    "type": "string",
                    "enum": ["node", "anvil"],
                    "description": "Which container to restart",
                },
                "wait_seconds": {
                    "type": "integer",
                    "description": "Seconds to wait after restart before checking health (default 5)",
                    "default": 5,
                },
            },
            "required": ["component"],
        },
    },
    {
        "name": "pause_network",
        "description": (
            "Temporarily disconnect the Anvil container from the sandbox network to simulate "
            "a network partition. After `duration_seconds`, reconnects and checks node recovery. "
            "Use to verify the node handles L1 unavailability gracefully."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_seconds": {
                    "type": "integer",
                    "description": "How long (seconds) to keep Anvil disconnected (max 60)",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
]

# Merge into AGENT_TOOLS — call AGENT_TOOLS + CHAOS_TOOLS when mode == 'chaos'
