"""Read-only observability tools.

None of these mutate the database. They are intended to be invoked by
the agentic loop when the model is reasoning about a running system.
"""

from __future__ import annotations

from ._compat import BaseDbTool
from .base import ToolContext, ToolMatch
from .formatting import print_rows


class ActiveSessionsTool(BaseDbTool):
    name = "active_sessions"
    description = "Show currently active user sessions from V$SESSION."
    examples = ("show active sessions", "what is SCOTT doing right now")
    mutating = False
    requires_approval = False
    parameters = {
        "type": "object",
        "properties": {
            "username": {
                "type": "string",
                "description": "Optional Oracle username (uppercased). Omit to list all active sessions.",
            },
            "min_seconds_in_wait": {
                "type": "integer",
                "description": "Only include sessions waiting at least this many seconds. Default 0.",
            },
        },
    }

    def match(self, prompt: str) -> ToolMatch | None:
        text = prompt.lower()
        if "active session" in text or "active sessions" in text:
            return ToolMatch(confidence=85)
        if "what is" in text and "doing" in text:
            return ToolMatch(confidence=70)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        # The agentic loop passes parsed arguments; the keyword-routed path
        # falls back to "no filter".
        username = None
        sessions = context.db.get_active_sessions(username=username)
        rows = [
            {
                "sid": s.sid,
                "serial": s.serial,
                "username": s.username or "N/A",
                "status": s.status,
                "sql_id": s.sql_id or "N/A",
                "prev_sql_id": s.prev_sql_id or "N/A",
                "event": s.event or "N/A",
                "machine": s.machine or "N/A",
                "program": s.program or "N/A",
                "seconds_in_wait": s.seconds_in_wait if s.seconds_in_wait is not None else 0,
            }
            for s in sessions
        ]
        print_rows(rows)
        return 0


class TopSqlTool(BaseDbTool):
    name = "top_sql"
    description = "Show top SQL by elapsed, cpu, gets, or reads from V$SQL."
    examples = ("show top sql by elapsed",)
    mutating = False
    requires_approval = False
    parameters = {
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "description": "One of: elapsed, cpu, gets, reads.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of rows to return. Default 10.",
            },
        },
        "required": ["metric"],
    }

    def match(self, prompt: str) -> ToolMatch | None:
        text = prompt.lower()
        if "top sql" in text or "top queries" in text or "expensive sql" in text:
            return ToolMatch(confidence=85)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        # When invoked through the keyword router, default to elapsed.
        metric = "elapsed"
        limit = 10
        rows = [
            {
                "sql_id": s.sql_id,
                "executions": s.executions,
                "elapsed_s": round(s.elapsed_seconds or 0.0, 2),
                "cpu_s": round(s.cpu_seconds or 0.0, 2),
                "buffer_gets": s.buffer_gets,
                "disk_reads": s.disk_reads,
                "sql_text": (s.sql_text or "")[:120],
            }
            for s in context.db.get_top_sql(metric=metric, limit=limit)
        ]
        print_rows(rows)
        return 0


class RedoSwitchesTool(BaseDbTool):
    name = "redo_switches"
    description = "Show hourly redo log switch counts from V$LOG_HISTORY."
    examples = ("show redo switches last 24 hours",)
    mutating = False
    requires_approval = False
    parameters = {
        "type": "object",
        "properties": {
            "hours": {
                "type": "integer",
                "description": "Look-back window in hours. Default 24.",
            },
        },
    }

    def match(self, prompt: str) -> ToolMatch | None:
        text = prompt.lower()
        if "redo" in text and ("switch" in text or "switches" in text):
            return ToolMatch(confidence=85)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        rows = [
            {"hour": r.day, "switches": r.switches}
            for r in context.db.get_redo_switches(hours=24)
        ]
        print_rows(rows)
        return 0


class WaitEventsTool(BaseDbTool):
    name = "wait_events"
    description = "Show top non-idle wait events from V$SYSTEM_EVENT."
    examples = ("show top wait events",)
    mutating = False
    requires_approval = False
    parameters = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of events to return. Default 10.",
            },
        },
    }

    def match(self, prompt: str) -> ToolMatch | None:
        text = prompt.lower()
        if "wait event" in text or "wait events" in text:
            return ToolMatch(confidence=90)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        rows = [
            {
                "event": w.event,
                "total_waits": w.total_waits,
                "time_waited_s": round(w.time_waited_seconds, 2),
                "avg_wait_ms": round(w.average_wait_ms, 2),
            }
            for w in context.db.get_top_wait_events(limit=10)
        ]
        print_rows(rows)
        return 0


class UserActivityTool(BaseDbTool):
    name = "user_activity"
    description = "Show what a given Oracle user is doing right now: active sessions plus their current SQL text."
    examples = ("what is SCOTT doing", "is SCOTT active")
    mutating = False
    requires_approval = False
    parameters = {
        "type": "object",
        "properties": {
            "username": {
                "type": "string",
                "description": "Oracle username (uppercased).",
            },
        },
        "required": ["username"],
    }

    def match(self, prompt: str) -> ToolMatch | None:
        text = prompt.lower()
        if ("doing" in text or "active" in text) and "user" in text:
            return ToolMatch(confidence=75)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        from oracle_db_agent.db import normalize_username

        from .parsing import extract_username

        username = extract_username(prompt) or input("Which username? ").strip()
        username = normalize_username(username)
        sessions = context.db.get_active_sessions(username=username)
        if not sessions:
            print(f"No active sessions for {username}.")
            return 0
        for s in sessions:
            print(f"Session {s.sid},{s.serial} — {s.status} — wait {s.seconds_in_wait}s — {s.event or 'no event'}")
            if s.sql_id:
                text = context.db.get_session_sql(s.sid)
                if text:
                    snippet = text[:400].replace("\n", " ")
                    print(f"  current SQL ({s.sql_id}): {snippet}")
        return 0


class ExplainSqlTool(BaseDbTool):
    name = "explain_sql"
    description = "Run EXPLAIN PLAN for a single SELECT/WITH statement and return the plan."
    examples = ("explain plan for select * from scott.emp",)
    mutating = False
    requires_approval = False
    parameters = {
        "type": "object",
        "properties": {
            "statement": {
                "type": "string",
                "description": "A single read-only SQL statement (SELECT or WITH ... SELECT).",
            },
        },
        "required": ["statement"],
    }

    def match(self, prompt: str) -> ToolMatch | None:
        text = prompt.lower()
        if "explain plan" in text or "explain query" in text:
            return ToolMatch(confidence=80)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        # When invoked from the keyword router, prompt the operator for the
        # statement. The agentic loop will pass it as an argument instead.
        statement = input("Statement to explain? ").strip()
        try:
            plan = context.db.explain_sql(statement)
        except Exception as exc:
            print(f"Could not explain: {exc}")
            return 1
        print(f"\nPlan for: {plan.statement}")
        for line in plan.plan_lines:
            print(line)
        return 0
