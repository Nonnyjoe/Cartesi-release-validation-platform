"""
services/ai-agent/agent_loop.py
The core observe → reason → act loop.
Drives Claude with streaming tool use and publishes events in real time.
Handles context compression at 80% window usage and hard limits.

Token economics: the system prompt (~15-20k tokens of project knowledge + skills)
and the tool schemas are identical on every turn, so both carry `cache_control`
breakpoints, plus a moving breakpoint on the latest tool_result message. After
turn 1 the entire stable prefix is served from Anthropic's prompt cache:
cache reads are ~10% of normal input price and do NOT count toward the
input-tokens/min rate limit (which is what killed earlier sessions with 429s).
`total_tokens` reported to the DB/UI counts billable work (uncached input +
cache writes + output); cache reads are tracked separately.
"""
import asyncio
import json
import logging
import os
import time
from typing import AsyncIterator, Callable, Any

import anthropic
import httpx

from tools import AGENT_TOOLS, CHAOS_TOOLS
from tools.reporting import get_all_findings
from tool_executor import ToolExecutor

log = logging.getLogger("ai-agent.loop")

FALLBACK_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL       = "claude-opus-4-6"
MAX_TOKENS          = 8096
CONTEXT_WINDOW      = 200_000
COMPRESS_THRESHOLD  = 0.80    # compress history when 80% of window used

# Reproducibility (2026-06-13 review): temperature=0 makes a run as deterministic
# as the API allows, and the resolved model id + params are stamped on every
# verdict. MODEL_SNAPSHOTS pins a stable alias to a dated snapshot when one is
# configured (env override AI_MODEL_<ALIAS>); absent that it resolves to itself.
AI_TEMPERATURE = float(os.environ.get("AI_TEMPERATURE", "0"))


def resolve_model_snapshot(model: str) -> str:
    """Map a model alias to a pinned dated snapshot if one is configured."""
    env_key = "AI_MODEL_" + model.upper().replace("-", "_").replace(".", "_")
    return os.environ.get(env_key, model)

# Hard limits per mode
LIMITS = {
    "autonomous":    {"max_tool_calls": 50,  "max_duration": 600},
    "collaborative": {"max_tool_calls": 200, "max_duration": 3600},
    "interactive":   {"max_tool_calls": 200, "max_duration": 3600},
        "chaos":        {"max_tool_calls": 100, "max_duration": 1800},
}

# Transient API errors (429 / 5xx / connection drops) are retried with backoff
# instead of failing the whole session.
RETRY_DELAYS_S = (5, 15, 30)

# Tool results streamed over the WS are truncated — the full output is always
# available in the ai.tool_invocations audit panel.
WS_RESULT_PREVIEW_CHARS = 3000

# Tool results fed back into the model context are bounded too: a single
# read_logs/cli-help output can be tens of KB (~5-10k tokens) and the
# conversation re-pays it on every later cache write. The audit table keeps
# the full output; the model gets a SHAPED version:
#   1. long hex strings keep head+tail+length (verification still works —
#      the agent knows what it sent; head/tail/length identifies a match),
#   2. then the whole serialisation is middle-truncated if still oversized.
MODEL_TOOL_RESULT_MAX_CHARS = int(os.environ.get("AI_TOOL_RESULT_MAX_CHARS", "5000"))
HEX_KEEP_HEAD  = 96
HEX_KEEP_TAIL  = 24
HEX_SHAPE_OVER = 200   # only shape hex strings longer than this


def _shape_value(v):
    """Recursively compact long hex strings inside a tool result."""
    if isinstance(v, str):
        if v.startswith("0x") and len(v) > HEX_SHAPE_OVER and all(
                c in "0123456789abcdefABCDEF" for c in v[2:]):
            return (f"{v[:HEX_KEEP_HEAD]}…{v[-HEX_KEEP_TAIL:]}"
                    f" [hex truncated, total {len(v)} chars — full value in audit panel]")
        return v
    if isinstance(v, dict):
        return {k: _shape_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_shape_value(x) for x in v]
    return v


def _bounded_tool_content(result) -> str:
    """Shape + JSON-serialise a tool result, truncating the middle when oversized."""
    try:
        result = _shape_value(result)
    except Exception:
        pass
    s = json.dumps(result, default=str)
    if len(s) <= MODEL_TOOL_RESULT_MAX_CHARS:
        return s
    head = MODEL_TOOL_RESULT_MAX_CHARS * 7 // 10
    tail = MODEL_TOOL_RESULT_MAX_CHARS * 2 // 10
    omitted = len(s) - head - tail
    return (
        s[:head]
        + f" …[TRUNCATED {omitted} chars — full output is in the tool audit panel]… "
        + s[-tail:]
    )


class AgentLoop:
    """
    Manages a single Claude agentic session with streaming output.

    Usage:
        loop = AgentLoop(system_prompt, executor, mode, on_event)
        await loop.run(initial_user_message)
    """

    def __init__(
        self,
        system_prompt: str,
        executor: ToolExecutor,
        mode: str,
        on_event: Callable[[dict], None],   # called for each streamed event
        api_key: str | None = None,
        model: str | None = None,
        max_tool_calls: int | None = None,   # per-session override (manual execution
                                             # needs ~10 calls per selected test)
        max_duration: int | None = None,     # seconds; paired override for long manual plans
        exclude_tools: list[str] | None = None,  # tool schemas to omit (saves prompt
                                                 # tokens + removes forbidden choices)
    ):
        self.system_prompt  = system_prompt
        self.executor       = executor
        self.mode           = mode
        self.on_event       = on_event
        self.model          = resolve_model_snapshot(model or DEFAULT_MODEL)
        # Stamped on every verdict for reproducibility (see review §8).
        self.model_params   = {"temperature": AI_TEMPERATURE, "max_tokens": MAX_TOKENS}
        self.max_tool_calls_override = max_tool_calls
        self.max_duration_override   = max_duration
        self.messages: list[dict] = []
        self.compression_summaries: list[dict] = []
        self.tool_call_count   = 0
        self.total_tokens      = 0   # billable: uncached input + cache writes + output
        self.cache_read_tokens = 0   # served from prompt cache (cheap, not rate-limited)
        self.context_tokens    = 0   # full context size of the last turn (for compression)
        self.start_time      = time.monotonic()
        self._client         = anthropic.AsyncAnthropic(
            api_key=api_key or FALLBACK_ANTHROPIC_API_KEY,
        )

        # Static across the session → cacheable prefix. The system prompt is sent
        # as a block with a cache breakpoint; the last tool schema carries one too
        # so the whole tools array lands in the same cached prefix.
        self._system_blocks = [{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }]
        base_tools = AGENT_TOOLS + CHAOS_TOOLS if mode == "chaos" else AGENT_TOOLS
        dropped = set(exclude_tools or [])
        self._tools = [dict(t) for t in base_tools if t["name"] not in dropped]
        if dropped:
            log.info("Tool schemas excluded for this session: %s", sorted(dropped))
        if self._tools:
            self._tools[-1] = {**self._tools[-1], "cache_control": {"type": "ephemeral"}}

    @property
    def _limits(self) -> dict:
        base = dict(LIMITS.get(self.mode, LIMITS["autonomous"]))
        if self.max_tool_calls_override:
            base["max_tool_calls"] = self.max_tool_calls_override
        if self.max_duration_override:
            base["max_duration"] = self.max_duration_override
        return base

    @property
    def _elapsed(self) -> float:
        return time.monotonic() - self.start_time

    def _over_limit(self) -> str | None:
        if self.tool_call_count >= self._limits["max_tool_calls"]:
            return f"Tool call limit reached ({self._limits['max_tool_calls']})"
        if self._elapsed >= self._limits["max_duration"]:
            return f"Time limit reached ({self._limits['max_duration']}s)"
        return None

    async def run(self, initial_message: str) -> dict:
        """
        Start the agentic loop with an initial user message.
        Returns a summary dict when the session ends.
        """
        self.messages = [{"role": "user", "content": initial_message}]
        self.start_time = time.monotonic()

        self.on_event({"type": "session_started", "mode": self.mode})

        while True:
            # Check hard limits before each turn
            limit_reason = self._over_limit()
            if limit_reason:
                log.warning("Session limit hit: %s", limit_reason)
                self.on_event({"type": "limit_reached", "reason": limit_reason})
                break

            # Compress context if approaching window limit. Uses the actual
            # context size of the last turn (incl. cached tokens) — NOT the
            # cumulative billing counter, which over-triggered compression.
            if self.context_tokens > CONTEXT_WINDOW * COMPRESS_THRESHOLD:
                await self._compress_context()

            # Stream a Claude response
            stop_reason, new_messages = await self._stream_turn()
            self.messages.extend(new_messages)

            if stop_reason == "end_turn":
                # Claude finished without tool calls — session complete
                self.on_event({"type": "session_complete"})
                break

            if stop_reason != "tool_use":
                log.warning("Unexpected stop_reason: %s", stop_reason)
                break

        findings = get_all_findings()
        return {
            "tool_call_count":   self.tool_call_count,
            "total_tokens":      self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "elapsed_seconds":   int(self._elapsed),
            "findings":          findings,
            "findings_count":    len(findings),
            "mode":              self.mode,
        }

    def _apply_message_cache_breakpoint(self):
        """Move a cache breakpoint to the last block of the latest list-content
        message so the whole conversation prefix is cache-read next turn."""
        last_marked = None
        for msg in self.messages:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        block.pop("cache_control", None)
                        last_marked = block
        if last_marked is not None:
            last_marked["cache_control"] = {"type": "ephemeral"}

    async def _stream_turn(self) -> tuple[str, list[dict]]:
        """
        Stream one Claude turn. Handles text deltas and tool use blocks.
        Retries transient API errors (429/5xx/connection) with backoff.
        Returns (stop_reason, new_messages_to_append).
        """
        new_messages: list[dict] = []
        tool_calls: list[dict]   = []
        current_text = ""
        stop_reason  = "end_turn"
        final        = None

        self._apply_message_cache_breakpoint()

        for attempt, delay in enumerate((0,) + RETRY_DELAYS_S):
            if delay:
                log.warning("Retrying Claude call in %ds (attempt %d)", delay, attempt + 1)
                self.on_event({"type": "ai.retry", "delay_s": delay, "attempt": attempt + 1})
                await asyncio.sleep(delay)
            try:
                current_text = ""
                async with self._client.messages.stream(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    temperature=AI_TEMPERATURE,
                    system=self._system_blocks,
                    tools=self._tools,
                    messages=self.messages,
                ) as stream:
                    async for event in stream:
                        if event.type == "content_block_delta":
                            delta = event.delta
                            if hasattr(delta, "text"):
                                current_text += delta.text
                                self.on_event({"type": "text_delta", "text": delta.text})
                            elif hasattr(delta, "partial_json"):
                                # Tool input streaming — accumulated by SDK
                                pass

                        elif event.type == "message_delta":
                            if hasattr(event.delta, "stop_reason"):
                                stop_reason = event.delta.stop_reason or "end_turn"

                    # Get the final message after streaming completes
                    final = await stream.get_final_message()
                break
            except (anthropic.RateLimitError, anthropic.InternalServerError,
                    anthropic.APIConnectionError,
                    # Mid-stream transport drops surface as raw httpx errors
                    # ("peer closed connection without sending complete message
                    # body") — retrying re-sends the turn; tool state is safe
                    # because results only commit after a complete final message.
                    httpx.RemoteProtocolError, httpx.ReadError,
                    httpx.ReadTimeout) as exc:
                log.warning("Transient Claude API error (attempt %d): %s", attempt + 1, exc)
                if attempt >= len(RETRY_DELAYS_S):
                    raise
                continue

        if final is None:  # defensive — loop above either breaks or raises
            raise RuntimeError("Claude stream produced no final message")

        # ── Usage accounting ───────────────────────────────────────────────
        u = final.usage
        cache_read   = getattr(u, "cache_read_input_tokens", 0) or 0
        cache_create = getattr(u, "cache_creation_input_tokens", 0) or 0
        self.total_tokens      += u.input_tokens + u.output_tokens + cache_create
        self.cache_read_tokens += cache_read
        self.context_tokens     = u.input_tokens + cache_read + cache_create
        log.info("Turn usage: in=%d out=%d cache_write=%d cache_read=%d (context=%d)",
                 u.input_tokens, u.output_tokens, cache_create, cache_read,
                 self.context_tokens)

        # Build assistant message from content blocks
        assistant_content = []
        for block in final.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type":  "tool_use",
                    "id":    block.id,
                    "name":  block.name,
                    "input": block.input,
                })
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

        new_messages.append({"role": "assistant", "content": assistant_content})

        # Execute all tool calls and build tool_result message
        if tool_calls:
            tool_results = []
            for tc in tool_calls:
                self.tool_call_count += 1
                self.on_event({
                    "type":       "tool_call",
                    "tool_name":  tc["name"],
                    "tool_input": tc["input"],
                    "call_number": self.tool_call_count,
                })

                result = await self.executor.execute(tc["name"], tc["input"])

                # WS event carries a bounded preview; the audit panel has the full output.
                preview = result
                try:
                    serialized = json.dumps(result, default=str)
                    if len(serialized) > WS_RESULT_PREVIEW_CHARS:
                        preview = {"truncated": True,
                                   "preview": serialized[:WS_RESULT_PREVIEW_CHARS]}
                except Exception:
                    preview = {"truncated": True, "preview": str(result)[:WS_RESULT_PREVIEW_CHARS]}
                self.on_event({
                    "type":        "tool_result",
                    "tool_name":   tc["name"],
                    "tool_output": preview,
                })

                # Surface findings on the live stream as first-class events.
                if tc["name"] == "report_finding" and isinstance(result, dict) \
                        and result.get("success"):
                    self.on_event({
                        "type":        "finding",
                        "severity":    tc["input"].get("severity", "info"),
                        "title":       tc["input"].get("title", ""),
                        "description": tc["input"].get("description", ""),
                    })

                # Surface manual-execution verdicts on the live stream too.
                if tc["name"] == "record_test_verdict" and isinstance(result, dict) \
                        and result.get("success"):
                    self.on_event({
                        "type":            "verdict",
                        "definition_slug": tc["input"].get("definition_slug", ""),
                        "verdict":         tc["input"].get("verdict", ""),
                        "reasoning":       tc["input"].get("reasoning", "")[:500],
                    })

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": tc["id"],
                    "content":     _bounded_tool_content(result),
                })

            new_messages.append({"role": "user", "content": tool_results})

        return stop_reason, new_messages

    async def _compress_context(self):
        """
        Summarise old conversation turns when approaching the context limit.
        Keeps the system prompt and last 4 messages intact.
        """
        if len(self.messages) <= 6:
            return

        log.info("Compressing context (context_tokens=%d, threshold=%d)",
                 self.context_tokens, int(CONTEXT_WINDOW * COMPRESS_THRESHOLD))

        # Ask Claude to summarise old turns
        to_summarise = self.messages[:-4]
        summary_prompt = (
            "Summarise the following conversation history concisely, "
            "preserving all key findings, tool results, and decisions:\n\n"
            + json.dumps(to_summarise)
        )
        resp = await self._client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=AI_TEMPERATURE,
            messages=[{"role": "user", "content": summary_prompt}],
        )
        summary_text = resp.content[0].text

        # Persist the summary so compressed-away turns are not lost from the
        # audit record (review §10 — irreversible mid-session information loss).
        self.compression_summaries.append({
            "at_message_index": len(self.messages) - 4,
            "summary": summary_text,
        })

        # Replace old messages with summary
        self.messages = (
            [{"role": "user", "content": f"[Context summary from earlier in this session]\n{summary_text}"},
             {"role": "assistant", "content": "Understood. I'll continue from where we left off."}]
            + self.messages[-4:]
        )
        # Billing counter (total_tokens) is cumulative and untouched; only the
        # live context-size estimate shrinks after compression.
        self.context_tokens = int(self.context_tokens * 0.4)
        self.on_event({"type": "context_compressed", "summary_length": len(summary_text)})
        log.info("Context compressed. New message count: %d", len(self.messages))

    def transcript(self, max_chars: int = 400_000) -> dict:
        """JSON-safe reasoning transcript for persistence to ai.sessions.
        Strips cache_control markers; bounds total size. Includes any
        context-compression summaries so nothing summarised away is lost."""
        def _clean(block):
            if isinstance(block, dict):
                return {k: _clean(v) for k, v in block.items() if k != "cache_control"}
            if isinstance(block, list):
                return [_clean(b) for b in block]
            return block
        msgs = _clean(self.messages)
        s = json.dumps(msgs, default=str)
        truncated = len(s) > max_chars
        return {
            # Full structured messages when within budget; otherwise a tail of the
            # serialised transcript (older turns are also in ai.tool_invocations).
            "messages": msgs if not truncated else None,
            "tail_raw": s[-max_chars:] if truncated else None,
            "truncated": truncated,
            "compression_summaries": self.compression_summaries,
        }

    async def send_user_message(self, text: str):
        """
        Inject a user message mid-session (collaborative / interactive modes).
        Returns after Claude responds (may include tool calls).
        """
        self.messages.append({"role": "user", "content": text})
        stop_reason, new_messages = await self._stream_turn()
        self.messages.extend(new_messages)
        return stop_reason
