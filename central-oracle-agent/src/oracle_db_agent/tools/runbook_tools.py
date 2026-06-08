"""Tools that read runbooks from `target.runbook_dir`.

The agentic loop uses these to discover what procedures are available and
to load one when the user asks the agent to "follow" a runbook.
"""

from __future__ import annotations

from oracle_db_agent.audit import AuditLog
from oracle_db_agent.runbooks import RunbookStore

from .base import ToolContext, ToolMatch


class ListRunbooksTool:
    name = "list_runbooks"
    description = "List runbooks available in the target's runbook directory."
    examples = ("list runbooks", "what runbooks do we have")
    mutating = False
    requires_approval = False
    parameters = {
        "type": "object",
        "properties": {},
    }

    def match(self, prompt: str) -> ToolMatch | None:
        return None  # only invoked by the loop, not by keyword routing

    def run(self, prompt: str, context: ToolContext) -> int:
        store = RunbookStore(context.options.target.runbook_dir)
        books = store.list()
        if not books:
            print(f"No runbooks found in {context.options.target.runbook_dir}.")
            return 0
        for book in books:
            params = ", ".join(p.name for p in book.parameters) or "(no parameters)"
            print(f"- {book.name}: {book.title} (params: {params})")
        return 0


class GetRunbookTool:
    name = "get_runbook"
    description = "Load the full text of a runbook by name."
    examples = ("load runbook kill_blocker",)
    mutating = False
    requires_approval = False
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Runbook filename without the .md suffix, e.g. 'kill_blocker'.",
            },
        },
        "required": ["name"],
    }

    def match(self, prompt: str) -> ToolMatch | None:
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        store = RunbookStore(context.options.target.runbook_dir)
        name = input("Runbook name? ").strip()
        book = store.get(name)
        if book is None:
            print(f"Runbook '{name}' not found in {context.options.target.runbook_dir}.")
            return 1
        print(f"# {book.title}")
        if book.parameters:
            for p in book.parameters:
                print(f"# param: {p.name} ({p.type}, default={p.default}) — {p.description}")
        print()
        print(book.body)
        return 0


def list_runbooks_for_loop(runbook_dir: str, audit: AuditLog | None = None) -> list[dict[str, object]]:
    """Return runbooks as JSON-serializable dicts for the agentic loop."""

    store = RunbookStore(runbook_dir)
    books = store.list()
    if audit is not None:
        audit.record(-1, "runbooks_listed", {"count": len(books)})
    return [
        {
            "name": b.name,
            "title": b.title,
            "parameters": [
                {"name": p.name, "type": p.type, "default": p.default, "description": p.description}
                for p in b.parameters
            ],
        }
        for b in books
    ]


def get_runbook_for_loop(
    runbook_dir: str,
    name: str,
    audit: AuditLog | None = None,
) -> dict[str, object] | None:
    """Return a runbook as a JSON-serializable dict, or None if missing."""

    store = RunbookStore(runbook_dir)
    book = store.get(name)
    if book is None:
        if audit is not None:
            audit.record(-1, "runbook_missing", {"name": name})
        return None
    if audit is not None:
        audit.record(-1, "runbook_loaded", {"name": name})
    return {
        "name": book.name,
        "title": book.title,
        "parameters": [
            {"name": p.name, "type": p.type, "default": p.default, "description": p.description}
            for p in book.parameters
        ],
        "body": book.body,
    }
