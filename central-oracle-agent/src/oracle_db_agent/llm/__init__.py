"""LLM provider interface and implementations for the agentic loop.

The loop talks to a small Protocol (`LlmClient`) that returns chat
completions with optional tool calls. Ollama is the supported backend in v1;
the interface is shaped so other providers (OpenAI, Anthropic, llama.cpp) can
be added without touching the loop.
"""

from .base import ChatMessage, LlmClient, LlmResponse, ToolCall, ToolSpec
from .ollama import OllamaClient, OllamaError
from .prompts import build_system_prompt

__all__ = [
    "ChatMessage",
    "LlmClient",
    "LlmResponse",
    "OllamaClient",
    "OllamaError",
    "ToolCall",
    "ToolSpec",
    "build_system_prompt",
]
