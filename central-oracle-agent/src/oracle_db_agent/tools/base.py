from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from oracle_db_agent.agent_options import AgentOptions
from oracle_db_agent.db import OracleClient


@dataclass(frozen=True)
class ToolContext:
    db: OracleClient
    options: AgentOptions
    run_id: str = "default"


@dataclass(frozen=True)
class ToolMatch:
    confidence: int
    reason: str = ""


class DbTool(Protocol):
    """Contract every tool implements.

    `parameters` is a JSON Schema object describing the tool's arguments.
    The agentic loop passes parsed arguments through `**arguments` to
    `run_with_arguments`; the keyword-routed path falls through to
    `run(prompt, context)`.

    `requires_approval` is True for mutating tools. The loop calls
    `ask_approval` before invoking any such tool; the keyword-routed path
    still calls it itself (existing behavior).
    """

    name: str
    description: str
    examples: tuple[str, ...]
    mutating: bool
    requires_approval: bool
    parameters: dict[str, Any]

    def match(self, prompt: str) -> ToolMatch | None:
        ...

    def run(self, prompt: str, context: ToolContext) -> int:
        ...

    def run_with_arguments(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> int:
        ...
