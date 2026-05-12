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
            "Read stdout/stderr logs from a sandbox container. "
            "Use 'node' to read the Cartesi rollups node logs, "
            "'anvil' to read Anvil chain logs. "
            "Essential for diagnosing failures and confirming expected behaviour."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "component": {
                    "type": "string",
                    "enum": ["node", "anvil"],
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
            "Execute a raw Foundry cast command against the Anvil chain. "
            "Provide everything after 'cast', e.g. 'block-number' or "
            "'call 0x59b2... \"inputs()\" --rpc-url ...'. "
            "The --rpc-url flag is added automatically if not present."
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
