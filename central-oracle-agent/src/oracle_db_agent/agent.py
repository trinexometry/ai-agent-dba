from __future__ import annotations

from .agent_options import AgentOptions
from .db import OracleClient
from .tools import ToolContext, ToolRegistry, default_registry


class OracleAgent:
    def __init__(
        self,
        db: OracleClient,
        options: AgentOptions,
        registry: ToolRegistry | None = None,
    ):
        self.db = db
        self.options = options
        self.registry = registry or default_registry()

    def run(self, prompt: str) -> int:
        selection = self.registry.select(prompt)
        if selection is None:
            print("I could not map that prompt to a supported operation.")
            self.registry.print_supported_tools()
            return 2

        context = ToolContext(db=self.db, options=self.options)
        return selection.tool.run(prompt, context)
