"""
services/ai-agent/model_clients/factory.py

Returns the appropriate ModelClient based on MODEL_PROVIDER env var.
"""
import os

from .base import ModelClient
from .anthropic_client import AnthropicClient
from .ollama_client import OllamaClient


def get_model_client() -> ModelClient:
    provider = os.getenv("MODEL_PROVIDER", "anthropic").lower()
    if provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "llama3.1")
        return OllamaClient(model=model)
    # Default: Anthropic
    model = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-6")
    return AnthropicClient(model=model)
