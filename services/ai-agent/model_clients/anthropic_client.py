"""
services/ai-agent/model_clients/anthropic_client.py

Thin wrapper around the Anthropic SDK that adapts it to the ModelClient interface.
"""
from __future__ import annotations
import os
from typing import AsyncGenerator

import anthropic

from .base import ModelClient, StreamEvent

_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


class AnthropicClient(ModelClient):
    def __init__(self, model: str = "claude-opus-4-6"):
        self.model = model

    async def stream_response(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 8192,
    ) -> AsyncGenerator[StreamEvent, None]:
        async with _client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        ) as stream:
            current_tool: dict | None = None
            current_tool_json = ""

            async for event in stream:
                etype = event.type

                if etype == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool = {"id": block.id, "name": block.name}
                        current_tool_json = ""

                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield {"type": "text", "text": delta.text}
                    elif delta.type == "input_json_delta":
                        current_tool_json += delta.partial_json

                elif etype == "content_block_stop":
                    if current_tool:
                        import json
                        try:
                            tool_input = json.loads(current_tool_json) if current_tool_json else {}
                        except json.JSONDecodeError:
                            tool_input = {"raw": current_tool_json}
                        yield {
                            "type": "tool_use",
                            "id": current_tool["id"],
                            "name": current_tool["name"],
                            "input": tool_input,
                        }
                        current_tool = None
                        current_tool_json = ""

                elif etype == "message_delta":
                    if hasattr(event, "usage"):
                        pass  # usage tracked at message_stop

                elif etype == "message_stop":
                    final = await stream.get_final_message()
                    yield {
                        "type": "end",
                        "stop_reason": final.stop_reason,
                        "usage": {
                            "input_tokens": final.usage.input_tokens,
                            "output_tokens": final.usage.output_tokens,
                        },
                    }

    async def count_tokens(self, messages: list[dict], system: str) -> int:
        resp = await _client.messages.count_tokens(
            model=self.model,
            system=system,
            messages=messages,
        )
        return resp.input_tokens
