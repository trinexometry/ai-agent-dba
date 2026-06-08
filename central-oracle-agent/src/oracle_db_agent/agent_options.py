from __future__ import annotations

from dataclasses import dataclass

from .config import DatabaseTarget


@dataclass(frozen=True)
class AgentOptions:
    target: DatabaseTarget
    dry_run: bool = False
    assume_yes: bool = False
    llm_provider: str = "none"
