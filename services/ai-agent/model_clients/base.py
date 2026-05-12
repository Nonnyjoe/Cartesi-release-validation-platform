"""
services/ai-agent/model_clients/base.py

Abstract ModelClient interface.
All providers (Anthropic, Ollama, …) implement this protocol.

stream_response() is an async generator that yields StreamEvent dicts:
  {"type": "text",      "text": "…"}
  {"type": "tool_use",  "id": "…", "name": "…", "input": {…}}
  {"type": "tool_result_request", "tool_use_id": "…"}  # sentinel asking caller to run the tool
  {"type": "end",       "stop_reason": "…", "usage": {…}}
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncGenerator


StreamEvent = dict  # typed loosely; see docstring above for shape


class ModelClient(ABC):
    @abstractmethod
    async def stream_response(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 8192,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Yield StreamEvents for one turn of the conversation."""
        ...

    @abstractmethod
    async def count_tokens(self, messages: list[dict], system: str) -> int:
        """Estimate token usage for context-compression decisions."""
        ...
