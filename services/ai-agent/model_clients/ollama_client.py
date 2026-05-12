"""
services/ai-agent/model_clients/ollama_client.py

ModelClient implementation for Ollama local models.
Maps tool use to Ollama's function-calling format.

Supported models with tool use: llama3.1, mistral-nemo, qwen2.5-coder, etc.

Set env vars:
  MODEL_PROVIDER=ollama
  OLLAMA_BASE_URL=http://ollama:11434
  OLLAMA_MODEL=llama3.1
"""
from __future__ import annotations
import json
import os
from typing import AsyncGenerator

import httpx

from .base import ModelClient, StreamEvent

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.1")


def _tool_to_ollama(tool: dict) -> dict:
    """Convert Claude-style tool spec to Ollama function spec."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


def _messages_to_ollama(messages: list[dict], system: str) -> list[dict]:
    """Convert Anthropic message format to Ollama format."""
    result = [{"role": "system", "content": system}]
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            result.append({"role": role, "content": content})
        elif isinstance(content, list):
            # Handle tool_use and tool_result blocks
            text_parts = []
            for block in content:
                btype = block.get("type")
                if btype == "text":
                    text_parts.append(block["text"])
                elif btype == "tool_use":
                    result.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        }],
                    })
                elif btype == "tool_result":
                    tool_content = block.get("content", "")
                    if isinstance(tool_content, list):
                        tool_content = " ".join(
                            c.get("text", "") for c in tool_content if c.get("type") == "text"
                        )
                    result.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": str(tool_content),
                    })
            if text_parts:
                result.append({"role": role, "content": "\n".join(text_parts)})

    return result


class OllamaClient(ModelClient):
    def __init__(self, model: str = OLLAMA_MODEL):
        self.model = model
        self.base_url = OLLAMA_BASE_URL

    async def stream_response(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 8192,
    ) -> AsyncGenerator[StreamEvent, None]:
        ollama_messages = _messages_to_ollama(messages, system)
        ollama_tools = [_tool_to_ollama(t) for t in tools]

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "tools": ollama_tools,
            "stream": True,
            "options": {"num_predict": max_tokens},
        }

        async with httpx.AsyncClient(timeout=120, base_url=self.base_url) as client:
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                total_in = 0
                total_out = 0

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = chunk.get("message", {})
                    content = msg.get("content", "")
                    tool_calls = msg.get("tool_calls", [])

                    if content:
                        yield {"type": "text", "text": content}

                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        raw_args = fn.get("arguments", {})
                        if isinstance(raw_args, str):
                            try:
                                raw_args = json.loads(raw_args)
                            except json.JSONDecodeError:
                                raw_args = {}
                        yield {
                            "type": "tool_use",
                            "id": tc.get("id", f"ollama_{fn.get('name','')}"),
                            "name": fn.get("name", ""),
                            "input": raw_args,
                        }

                    if chunk.get("done"):
                        total_in = chunk.get("prompt_eval_count", 0)
                        total_out = chunk.get("eval_count", 0)
                        yield {
                            "type": "end",
                            "stop_reason": "end_turn",
                            "usage": {
                                "input_tokens": total_in,
                                "output_tokens": total_out,
                            },
                        }

    async def count_tokens(self, messages: list[dict], system: str) -> int:
        # Ollama doesn't expose a token counting endpoint — estimate by character count
        total_chars = len(system)
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    total_chars += len(str(block.get("text", "") or block.get("content", "")))
        return total_chars // 4  # rough estimate: 4 chars per token
