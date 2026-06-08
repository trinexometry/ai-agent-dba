from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from oracle_db_agent.agent_options import AgentOptions
from oracle_db_agent.db import OracleClient


@dataclass(frozen=True)
class ToolContext:
    db: OracleClient
    options: AgentOptions


@dataclass(frozen=True)
class ToolMatch:
    confidence: int
    reason: str = ""


class DbTool(Protocol):
    name: str
    description: str
    examples: tuple[str, ...]
    mutating: bool

    def match(self, prompt: str) -> ToolMatch | None:
        ...

    def run(self, prompt: str, context: ToolContext) -> int:
        ...
