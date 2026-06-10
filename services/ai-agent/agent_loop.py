"""
services/ai-agent/agent_loop.py
The core observe → reason → act loop.
Drives Claude with streaming tool use and publishes events in real time.
Handles context compression at 80% window usage and hard limits.
"""
import asyncio
import json
import logging
import os
import time
from typing import AsyncIterator, Callable, Any

import anthropic

from tools import AGENT_TOOLS, CHAOS_TOOLS
from tools.reporting import get_all_findings
from tool_executor import ToolExecutor

log = logging.getLogger("ai-agent.loop")

FALLBACK_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL       = "claude-opus-4-6"
MAX_TOKENS          = 8096
CONTEXT_WINDOW      = 200_000
COMPRESS_THRESHOLD  = 0.80    # compress history when 80% of window used

# Hard limits per mode
LIMITS = {
    "autonomous":    {"max_tool_calls": 50,  "max_duration": 600},
    "collaborative": {"max_tool_calls": 200, "max_duration": 3600},
    "interactive":   {"max_tool_calls": 200, "max_duration": 3600},
        "chaos":        {"max_tool_calls": 100, "max_duration": 1800},
}


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
    ):
        self.system_prompt  = system_prompt
        self.executor       = executor
        self.mode           = mode
        self.on_event       = on_event
        self.model          = model or DEFAULT_MODEL
        self.messages: list[dict] = []
        self.tool_call_count = 0
        self.total_tokens    = 0
        self.start_time      = time.monotonic()
        self._client         = anthropic.AsyncAnthropic(
            api_key=api_key or FALLBACK_ANTHROPIC_API_KEY,
        )

    @property
    def _limits(self) -> dict:
        return LIMITS.get(self.mode, LIMITS["autonomous"])

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

            # Compress context if approaching window limit
            if self.total_tokens > CONTEXT_WINDOW * COMPRESS_THRESHOLD:
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
            "tool_call_count": self.tool_call_count,
            "total_tokens":    self.total_tokens,
            "elapsed_seconds": int(self._elapsed),
            "findings":        findings,
            "findings_count":  len(findings),
            "mode":            self.mode,
        }

    async def _stream_turn(self) -> tuple[str, list[dict]]:
        """
        Stream one Claude turn. Handles text deltas and tool use blocks.
        Returns (stop_reason, new_messages_to_append).
        """
        new_messages: list[dict] = []
        tool_calls: list[dict]   = []
        current_text = ""
        stop_reason  = "end_turn"

        # Chaos sessions additionally get the fault-injection tools.
        tools = AGENT_TOOLS + CHAOS_TOOLS if self.mode == "chaos" else AGENT_TOOLS

        async with self._client.messages.stream(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=self.system_prompt,
            tools=tools,
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

                elif event.type == "content_block_stop":
                    block = event.content_block if hasattr(event, "content_block") else None

                elif event.type == "message_delta":
                    if hasattr(event.delta, "stop_reason"):
                        stop_reason = event.delta.stop_reason or "end_turn"

                elif event.type == "message_stop":
                    pass

            # Get the final message after streaming completes
            final = await stream.get_final_message()
            self.total_tokens += final.usage.input_tokens + final.usage.output_tokens

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

                self.on_event({
                    "type":        "tool_result",
                    "tool_name":   tc["name"],
                    "tool_output": result,
                })

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": tc["id"],
                    "content":     json.dumps(result),
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

        log.info("Compressing context (tokens=%d, threshold=%d)",
                 self.total_tokens, int(CONTEXT_WINDOW * COMPRESS_THRESHOLD))

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
            messages=[{"role": "user", "content": summary_prompt}],
        )
        summary_text = resp.content[0].text

        # Replace old messages with summary
        self.messages = (
            [{"role": "user", "content": f"[Context summary from earlier in this session]\n{summary_text}"},
             {"role": "assistant", "content": "Understood. I'll continue from where we left off."}]
            + self.messages[-4:]
        )
        self.total_tokens = int(self.total_tokens * 0.4)  # rough estimate post-compression
        self.on_event({"type": "context_compressed", "summary_length": len(summary_text)})
        log.info("Context compressed. New message count: %d", len(self.messages))

    async def send_user_message(self, text: str):
        """
        Inject a user message mid-session (collaborative / interactive modes).
        Returns after Claude responds (may include tool calls).
        """
        self.messages.append({"role": "user", "content": text})
        stop_reason, new_messages = await self._stream_turn()
        self.messages.extend(new_messages)
        return stop_reason
