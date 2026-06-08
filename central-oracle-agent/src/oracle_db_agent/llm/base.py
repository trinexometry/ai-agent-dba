"""Provider-neutral types for the agentic loop.

Kept tiny on purpose: a `LlmClient` is anything that takes a list of
messages and a tool catalog and returns a `LlmResponse`. The loop never
imports provider SDKs directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolSpec:
    """JSON-Schema-style description of a tool the LLM can call.

    `name` and `description` are required. `parameters` is a JSON Schema object
    (the Ollama `/api/chat` `tools` field accepts this shape directly). If
    the tool takes no arguments, pass `{"type": "object", "properties": {}}`.
    """

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation requested by the LLM.

    `arguments` is whatever the model produced; the loop hands it to the tool
    as `**arguments`. Tools are responsible for validating types.
    """

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatMessage:
    """One message in the conversation.

    `role` is one of `system`, `user`, `assistant`, `tool`. `tool_call_id` is
    only set for `role="tool"` messages and ties the observation back to the
    assistant message that requested it.
    """

    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LlmResponse:
    """One completion from the LLM.

    `is_final_answer` is True when the model returned a plain assistant
    message with no tool calls. `tool_calls` is empty in that case.
    """

    text: str
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)

    @property
    def is_final_answer(self) -> bool:
        return not self.tool_calls


class LlmClient(Protocol):
    """Minimal contract the loop depends on."""

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
    ) -> LlmResponse:
        ...
