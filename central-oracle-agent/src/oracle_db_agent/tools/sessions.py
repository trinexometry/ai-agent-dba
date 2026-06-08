from __future__ import annotations

from oracle_db_agent.approval import ApprovalRequest, ask_approval

from ._compat import BaseDbTool
from .base import ToolContext, ToolMatch
from .parsing import extract_sid_serial


class KillSessionTool(BaseDbTool):
    name = "kill_session"
    description = "Kill an Oracle session after showing session details."
    examples = ("kill session sid 123 serial 456",)
    mutating = True
    requires_approval = True
    parameters = {
        "type": "object",
        "properties": {
            "sid": {"type": "integer", "description": "Session ID."},
            "serial": {"type": "integer", "description": "Session serial number."},
            "immediate": {
                "type": "boolean",
                "description": "If true, kill IMMEDIATE. Default true.",
            },
        },
        "required": ["sid", "serial"],
    }

    def match(self, prompt: str) -> ToolMatch | None:
        text = prompt.lower()
        if "kill" in text and "session" in text:
            return ToolMatch(confidence=95)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        values = extract_sid_serial(prompt)
        if values is None:
            sid = int(input("SID? ").strip())
            serial = int(input("Serial#? ").strip())
        else:
            sid, serial = values

        session = context.db.get_session(sid, serial)
        if session is None:
            print(f"Session {sid},{serial} was not found in V$SESSION.")
            return 1

        print()
        print(f"Session {session.sid},{session.serial}")
        print(f"User: {session.username or 'N/A'}")
        print(f"Status: {session.status}")
        print(f"Machine: {session.machine or 'N/A'}")
        print(f"Program: {session.program or 'N/A'}")
        print(f"SQL ID: {session.sql_id or 'N/A'}")
        print(f"Event: {session.event or 'N/A'}")
        print(f"Blocking session: {session.blocking_session or 'N/A'}")

        sql = context.db.kill_session_sql(sid, serial, immediate=True)
        approved = ask_approval(
            ApprovalRequest(
                title=f"Kill Oracle session {sid},{serial}",
                details="This can interrupt active work and roll back the session transaction.",
                command=sql,
            ),
            assume_yes=context.options.assume_yes
            and not context.options.target.require_mutation_approval,
        )
        if not approved:
            print("Cancelled. No changes were made.")
            return 1
        if context.options.dry_run:
            print("Dry run enabled. No changes were made.")
            return 0

        context.db.kill_session(sid, serial, immediate=True)
        print("Kill session command executed.")
        return 0

    def run_with_arguments(self, arguments: dict, context: ToolContext) -> int:
        try:
            sid = int(arguments["sid"])
            serial = int(arguments["serial"])
        except (KeyError, TypeError, ValueError):
            print("kill_session requires 'sid' and 'serial' as integers")
            return 1
        return self.run(f"kill session sid {sid} serial {serial}", context)
