from __future__ import annotations

from dataclasses import dataclass

from .base import DbTool, ToolContext


@dataclass(frozen=True)
class ToolSelection:
    tool: DbTool
    confidence: int


class ToolRegistry:
    def __init__(self, tools: list[DbTool]):
        self.tools = tools

    def select(self, prompt: str) -> ToolSelection | None:
        matches: list[ToolSelection] = []
        for tool in self.tools:
            match = tool.match(prompt)
            if match is not None:
                matches.append(ToolSelection(tool=tool, confidence=match.confidence))
        if not matches:
            return None
        return max(matches, key=lambda item: item.confidence)

    def print_supported_tools(self) -> None:
        print("Supported operations:")
        for tool in self.tools:
            print(f"- {tool.name}: {tool.description}")
            if tool.examples:
                print(f"  example: {tool.examples[0]}")


def default_registry() -> ToolRegistry:
    from .awr import AnalyzeAwrTool
    from .health import (
        BlockingSessionsTool,
        InvalidObjectsTool,
        LongRunningSqlTool,
        TablespaceUsageTool,
    )
    from .sessions import KillSessionTool
    from .users import LockUserTool, ShowUserTool, UnlockUserTool

    return ToolRegistry(
        [
            ShowUserTool(),
            UnlockUserTool(),
            LockUserTool(),
            KillSessionTool(),
            BlockingSessionsTool(),
            LongRunningSqlTool(),
            TablespaceUsageTool(),
            InvalidObjectsTool(),
            AnalyzeAwrTool(),
        ]
    )


__all__ = ["ToolContext", "ToolRegistry", "default_registry"]
