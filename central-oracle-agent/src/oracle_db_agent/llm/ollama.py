"""Ollama HTTP client.

Talks to a local Ollama daemon at `POST /api/chat`. We deliberately use
`requests` rather than an SDK so the dependency tree stays small and so
the agentic loop has a clear, mockable HTTP boundary.

The Ollama chat API returns tool calls under `message.tool_calls` when
the model supports function calling. We parse that into our `ToolCall`
type. When `tool_calls` is absent we treat the response as a final answer.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from .base import ChatMessage, LlmClient, LlmResponse, ToolCall, ToolSpec

log = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Raised when the Ollama daemon returns an error or is unreachable."""


class OllamaClient:
    """Thin wrapper around `POST /api/chat`.

    Parameters
    ----------
    base_url
        Where the Ollama daemon listens. Defaults to localhost:11434.
    model
        Model name as shown by `ollama list`, e.g. `llama3.1:8b`.
    timeout
        Per-request timeout in seconds. Generous because the first call on
        a cold model can take a while; the loop has its own step budget.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ------------------------------------------------------------------ chat

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
    ) -> LlmResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_message_to_dict(m) for m in messages],
            "stream": False,
        }
        if tools:
            payload["tools"] = [_tool_to_dict(t) for t in tools]

        url = f"{self.base_url}/api/chat"
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise OllamaError(
                f"Ollama is not reachable at {self.base_url}: {exc}"
            ) from exc

        if response.status_code >= 500:
            raise OllamaError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
            )
        if response.status_code >= 400:
            # 4xx usually means the model is missing or the request is bad.
            # Surface the body so the operator can fix it.
            raise OllamaError(
                f"Ollama rejected the request (HTTP {response.status_code}): "
                f"{response.text[:200]}"
            )

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Ollama returned non-JSON body: {response.text[:200]}") from exc

        message = data.get("message") or {}
        text = str(message.get("content") or "")
        raw_calls = message.get("tool_calls") or []
        calls: list[ToolCall] = []
        for raw in raw_calls:
            fn = raw.get("function") or {}
            name = str(fn.get("name") or "")
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                # Some models return a JSON string instead of an object.
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            if name:
                calls.append(ToolCall(name=name, arguments=args))

        return LlmResponse(text=text, tool_calls=tuple(calls))


# ----------------------------------------------------------------- helpers


def _message_to_dict(message: ChatMessage) -> dict[str, Any]:
    out: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        out["tool_calls"] = [
            {
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                }
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id:
        out["tool_call_id"] = message.tool_call_id
    return out


def _tool_to_dict(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }
