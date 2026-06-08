"""Backwards-compatible shim.

The old entry point was `OracleAgent.run(prompt)`. The new entry point is
`AgenticLoop.run(prompt)` (see `agentic.py`). This module exists so any
external code that imported `OracleAgent` keeps working.
"""

from __future__ import annotations

from .agentic import AgenticLoop, build_ollama_loop
from .tools.registry import default_registry


class OracleAgent:
    """Deprecated. Use `agentic.AgenticLoop` directly."""

    def __init__(self, db, options, registry=None):
        registry = registry or default_registry()
        self.loop = build_ollama_loop(
            db=db,
            options=options,
            registry=registry,
            audit_dir=options.audit_dir,
        )

    def run(self, prompt: str) -> int:
        return self.loop.run(prompt)


__all__ = ["AgenticLoop", "OracleAgent"]
