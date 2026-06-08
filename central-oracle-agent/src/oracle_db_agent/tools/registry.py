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
        self._by_name = {tool.name: tool for tool in tools}

    def select(self, prompt: str) -> ToolSelection | None:
        matches: list[ToolSelection] = []
        for tool in self.tools:
            match = tool.match(prompt)
            if match is not None:
                matches.append(ToolSelection(tool=tool, confidence=match.confidence))
        if not matches:
            return None
        return max(matches, key=lambda item: item.confidence)

    def get(self, name: str) -> DbTool | None:
        return self._by_name.get(name)

    def names(self) -> list[str]:
        return [tool.name for tool in self.tools]

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
    from .observability import (
        ActiveSessionsTool,
        ExplainSqlTool,
        RedoSwitchesTool,
        TopSqlTool,
        UserActivityTool,
        WaitEventsTool,
    )
    from .runbook_tools import GetRunbookTool, ListRunbooksTool
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
            ActiveSessionsTool(),
            TopSqlTool(),
            RedoSwitchesTool(),
            WaitEventsTool(),
            UserActivityTool(),
            ExplainSqlTool(),
            ListRunbooksTool(),
            GetRunbookTool(),
            AnalyzeAwrTool(),
        ]
    )


__all__ = ["ToolContext", "ToolRegistry", "ToolSelection", "default_registry"]
