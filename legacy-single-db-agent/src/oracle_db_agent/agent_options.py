from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentOptions:
    dry_run: bool = False
    assume_yes: bool = False
    llm_provider: str = "none"
