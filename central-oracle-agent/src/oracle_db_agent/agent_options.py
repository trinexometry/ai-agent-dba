from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .config import DatabaseTarget


@dataclass(frozen=True)
class AgentOptions:
    target: DatabaseTarget
    dry_run: bool = False
    assume_yes: bool = False
    llm_provider: Literal["none", "ollama"] = "none"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    max_steps: int = 8
    explain: bool = False
    audit_dir: Path = field(default_factory=lambda: Path("audit"))
