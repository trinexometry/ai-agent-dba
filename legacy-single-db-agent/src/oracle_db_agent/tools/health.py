from __future__ import annotations

from .base import ToolContext, ToolMatch
from .formatting import print_rows
from .parsing import contains_any, extract_owner


class BlockingSessionsTool:
    name = "blocking_sessions"
    description = "Show sessions blocked by another session."
    examples = ("show blocking sessions",)
    mutating = False

    def match(self, prompt: str) -> ToolMatch | None:
        if contains_any(prompt, ("blocking session", "blocked session", "blockers", "blocking")):
            return ToolMatch(confidence=90)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        rows = context.db.get_blocking_sessions()
        print_rows(rows)
        return 0


class LongRunningSqlTool:
    name = "long_running_sql"
    description = "Show active long-running SQL operations from V$SESSION_LONGOPS."
    examples = ("show long running sql",)
    mutating = False

    def match(self, prompt: str) -> ToolMatch | None:
        text = prompt.lower()
        if "long" in text and ("sql" in text or "query" in text or "running" in text):
            return ToolMatch(confidence=85)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        rows = context.db.get_long_running_sql()
        print_rows(rows)
        return 0


class TablespaceUsageTool:
    name = "tablespace_usage"
    description = "Show tablespace used, free, total MB, and usage percentage."
    examples = ("show tablespace usage",)
    mutating = False

    def match(self, prompt: str) -> ToolMatch | None:
        if "tablespace" in prompt.lower() and contains_any(prompt, ("usage", "space", "free", "used", "show")):
            return ToolMatch(confidence=90)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        rows = [
            {
                "tablespace_name": item.tablespace_name,
                "used_mb": item.used_mb,
                "free_mb": item.free_mb,
                "total_mb": item.total_mb,
                "used_pct": item.used_pct,
            }
            for item in context.db.get_tablespace_usage()
        ]
        print_rows(rows)
        return 0


class InvalidObjectsTool:
    name = "invalid_objects"
    description = "Show invalid database objects, optionally filtered by schema."
    examples = ("show invalid objects in schema HR",)
    mutating = False

    def match(self, prompt: str) -> ToolMatch | None:
        text = prompt.lower()
        if "invalid" in text and ("object" in text or "objects" in text):
            return ToolMatch(confidence=90)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        owner = extract_owner(prompt)
        rows = [
            {
                "owner": item.owner,
                "object_name": item.object_name,
                "object_type": item.object_type,
                "status": item.status,
            }
            for item in context.db.get_invalid_objects(owner)
        ]
        print_rows(rows)
        return 0
