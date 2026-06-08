from __future__ import annotations

from oracle_db_agent.approval import ApprovalRequest, ask_approval
from oracle_db_agent.db import normalize_username

from ._compat import BaseDbTool
from .base import ToolContext, ToolMatch
from .parsing import contains_any, extract_username


def print_user_status(context: ToolContext, username: str) -> bool:
    status = context.db.get_user_status(username)
    if status is None:
        print(f"User {username} was not found in DBA_USERS.")
        return False

    print()
    print(f"Current status for {status.username}")
    print(f"Account status: {status.account_status}")
    print(f"Lock date: {status.lock_date or 'N/A'}")
    print(f"Expiry date: {status.expiry_date or 'N/A'}")
    print(f"Profile: {status.profile}")
    return True


class ShowUserTool(BaseDbTool):
    name = "show_user"
    description = "Show Oracle user account status, lock date, expiry date, and profile."
    examples = ("check user SCOTT status",)
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
        if "user" in prompt.lower() and contains_any(prompt, ("status", "check", "show", "describe")):
            return ToolMatch(confidence=70)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        username = extract_username(prompt) or input("Which username should I check? ").strip()
        username = normalize_username(username)
        return 0 if print_user_status(context, username) else 1

    def run_with_arguments(self, arguments: dict, context: ToolContext) -> int:
        username = arguments.get("username")
        if not username:
            print("show_user requires 'username'")
            return 1
        return 0 if print_user_status(context, normalize_username(str(username))) else 1


class UnlockUserTool(BaseDbTool):
    name = "unlock_user"
    description = "Unlock an Oracle user after showing current account status."
    examples = ("unlock user SCOTT",)
    mutating = True
    requires_approval = True
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
        if "unlock" in prompt.lower() and "user" in prompt.lower():
            return ToolMatch(confidence=100)
        if prompt.lower().startswith("unlock "):
            return ToolMatch(confidence=90)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        username = extract_username(prompt) or input("Which username should I unlock? ").strip()
        username = normalize_username(username)
        if not print_user_status(context, username):
            return 1

        sql = context.db.unlock_user_sql(username)
        approved = ask_approval(
            ApprovalRequest(
                title=f"Unlock Oracle user {username}",
                details="This changes only the account lock state. It does not reset the password.",
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

        context.db.unlock_user(username)
        print("User unlock completed.")
        print_user_status(context, username)
        return 0

    def run_with_arguments(self, arguments: dict, context: ToolContext) -> int:
        username = arguments.get("username")
        if not username:
            print("unlock_user requires 'username'")
            return 1
        return self.run(f"unlock user {username}", context)


class LockUserTool(BaseDbTool):
    name = "lock_user"
    description = "Lock an Oracle user after showing current account status."
    examples = ("lock user SCOTT",)
    mutating = True
    requires_approval = True
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
        if "unlock" in text:
            return None
        if "lock" in text and "user" in text:
            return ToolMatch(confidence=95)
        if text.startswith("lock "):
            return ToolMatch(confidence=85)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        username = extract_username(prompt) or input("Which username should I lock? ").strip()
        username = normalize_username(username)
        if not print_user_status(context, username):
            return 1

        sql = context.db.lock_user_sql(username)
        approved = ask_approval(
            ApprovalRequest(
                title=f"Lock Oracle user {username}",
                details="This prevents the account from logging in until it is unlocked.",
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

        context.db.lock_user(username)
        print("User lock completed.")
        print_user_status(context, username)
        return 0

    def run_with_arguments(self, arguments: dict, context: ToolContext) -> int:
        username = arguments.get("username")
        if not username:
            print("lock_user requires 'username'")
            return 1
        return self.run(f"lock user {username}", context)
