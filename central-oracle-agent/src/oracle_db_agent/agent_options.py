from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .config import DatabaseTarget


# Default model: small enough to run on 8 GB RAM laptops alongside Ollama.
# Override per-target in inventory.yml or with --model.
DEFAULT_OLLAMA_MODEL = "phi3:mini"


@dataclass(frozen=True)
class AgentOptions:
    target: DatabaseTarget
    dry_run: bool = False
    assume_yes: bool = False
    llm_provider: Literal["none", "ollama"] = "none"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    max_steps: int = 8
    explain: bool = False
    audit_dir: Path = field(default_factory=lambda: Path("audit"))
